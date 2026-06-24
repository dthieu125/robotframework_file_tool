"""
Test Case Executor - Executes individual test cases sequentially
Handles execution of test cases one by one and collects results
"""
import re
import subprocess
import logging
import shlex
import sys
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from robot.api import ExecutionResult
from robot.api.parsing import get_model
from robot.parsing.model.blocks import TestCaseSection

from test_case import TestCase

logger = logging.getLogger(__name__)

# Test Script Path template
# Strict full-match: [REPO:<non-empty>][PATH:<non-empty>] with nothing else allowed
RE_TEST_SCRIPT_PATH = re.compile(r"^\[REPO:(?P<repo>[^\]]+)\]\[PATH:(?P<path>[^\]]+)\]$")


@dataclass
class ExecutionOptions:
    """Options controlling a test collection execution run."""

    prefix: str = "TP"
    flatten_result: bool = False
    robot_args: Optional[str] = None


class TestCaseExecutor:
    """
    Executor for running test cases individually
    Each test case gets its own execution and output folder
    """

    def __init__(self, config: dict):
        """
        Initialize Test Case Executor

        Args:
            config: Configuration dictionary
        """
        self.config = config
        robot_config = config.get('robot', {})
        self.execution_config = robot_config.get('execution', {})

        self.output_directory = Path(robot_config.get('output_directory', 'reports'))
        self.output_directory.mkdir(parents=True, exist_ok=True)

        self.robot_executable = 'robot'
        self.rebot_executable = 'robot.rebot'
        self.custom_args = self.execution_config.get('custom_args', [])
        self.additional_args = self.execution_config.get('additional_args', [])

    def _check_testcase_exists(self, robot_file: Path, test_name: str) -> bool:
        """
        Check if a test case exists in the given robot file.

        Args:
            robot_file: Path to the .robot file
            test_name: Name of the test case to check

        Returns:
            bool: True if the test case exists, False otherwise
        """
        try:
            model = get_model(str(robot_file))
            return any(
                test.name == test_name
                for section in model.sections if isinstance(section, TestCaseSection)
                for test in section.body
                if hasattr(test, 'name')
            )
        except IOError as e:
            logger.error("Error reading robot file %s: %s", robot_file, str(e))
            return False

    def resolve_test_script_path(self, tc: TestCase, workspace: Path) -> Optional[Path]:
        """
        Resolve the full path of a Robot Framework file from an ETM test case.

        Resolution order:
        1. If raw_path matches exactly [REPO:<name>][PATH:<name>] -> resolve via workspace
        2. If raw_path is an absolute filesystem path that exists -> return it
        3. Otherwise -> return None (caller should mark the test case as error)

        Args:
            tc: TestCase object containing the test case details.
            workspace: Path to the workspace directory.

        Assumptions:
        - Windows-friendly workflow
        - Repo folder name = last segment of REPO

        Returns:
            The resolved path if successful, None otherwise.
        """
        raw_path = tc.test_script_path

        if not raw_path:
            return None

        raw_path = str(raw_path).strip() if isinstance(raw_path, Path) else raw_path

        # ------------------------------------------------------------------
        # 1. Test Script Path template: [REPO:<name>][PATH:<name>]
        #    Must match exactly — no extra text outside the brackets allowed.
        # ------------------------------------------------------------------
        match = RE_TEST_SCRIPT_PATH.match(raw_path)

        if match:
            repo_folder = Path(match.group("repo")).name
            return (workspace / repo_folder / match.group("path")).resolve()

        # ------------------------------------------------------------------
        # 2. Absolute filesystem path that actually exists on disk.
        #    Relative paths and malformed paths are rejected.
        # ------------------------------------------------------------------
        robot_file_path = Path(raw_path)

        if robot_file_path.is_absolute() and robot_file_path.is_file():
            return robot_file_path.resolve()

        return None

    # ------------------------------------------------------------------
    # Helpers extracted to keep run_testcase_from_test_collection concise
    # ------------------------------------------------------------------

    def _resolve_paths_for_testcases(self, testcases: List[TestCase], workspace: Path) -> None:
        """Resolve robot file paths for all test cases in-place."""
        for tc in testcases:
            try:
                resolved_path = self.resolve_test_script_path(tc, workspace)
                if resolved_path and resolved_path.exists():
                    tc.set_test_script_path(resolved_path)
                else:
                    error_msg = (
                        f"TC {tc.tcid}: {tc.test_name} - Robot file not found: {resolved_path}"
                        f". Robot file path is resolved from {tc.test_script_path}"
                    )
                    logger.error("TC %s - %s: Robot file not found", tc.tcid, tc.test_name)
                    tc.mark_as_error(error_msg)
            except Exception as e:  # pylint: disable=broad-except
                error_msg = f"Error resolving robot file path of test case {tc.tcid}: {e}"
                logger.error(error_msg)
                tc.mark_as_error(error_msg)

    def _group_testcases_by_file(self, testcases: List[TestCase]) -> Dict[str, dict]:
        """Group valid test cases (no errors) by their resolved robot file path."""
        groups: Dict[str, dict] = {}
        for testcase in testcases:
            if testcase.error_message:
                continue
            robot_file = testcase.test_script_path
            key = str(robot_file.resolve())
            if key not in groups:
                groups[key] = {'file': robot_file, 'testcases': []}
            groups[key]['testcases'].append(testcase)
        return groups

    def _log_execution_summary(self, testcases: List[TestCase], total: int) -> None:
        """Log a statistics table and per-error detail after execution."""
        passed = sum(1 for tc in testcases if "PASS" in tc.status.upper())
        failed = sum(1 for tc in testcases if "FAIL" in tc.status.upper())
        errored = sum(1 for tc in testcases if "ERROR" in tc.status.upper())
        pending = sum(1 for tc in testcases if "PENDING" in tc.status.upper())
        skipped = sum(1 for tc in testcases if "SKIP" in tc.status.upper())
        total_time = sum(tc.execution_time for tc in testcases)

        logger.info("%s EXECUTION SUMMARY %s", "="*30, "="*31)
        logger.info("TOTAL TEST CASES : %d", total)
        logger.info("TOTAL TIME       : %.2fs", total_time)
        logger.info("-" * 30)
        logger.info("%-15s | %-10s", "Status", "Count")
        logger.info("-" * 30)
        logger.info("%-15s | %-10d", "PASSED", passed)
        logger.info("%-15s | %-10d", "FAILED", failed)
        logger.info("%-15s | %-10d", "ERROR", errored)
        logger.info("%-15s | %-10d", "PENDING", pending)
        logger.info("%-15s | %-10d", "SKIPPED", skipped)
        logger.info("-" * 30)

        error_tcs = [tc for tc in testcases if tc.error_message]
        if error_tcs:
            logger.info("List of test cases with errors:")
            for i, tc in enumerate(error_tcs, 1):
                safe_msg = (tc.error_message
                            .replace("\n", "\\n")
                            .replace("\t", "\\t")
                            .replace("\r", "\\r"))
                logger.info("%d. %s", i, safe_msg)

    # ------------------------------------------------------------------
    # Public execution entry point
    # ------------------------------------------------------------------

    def run_testcase_from_test_collection(self,
                                          testcases: List[TestCase],
                                          exec_id: str,
                                          options: Optional[ExecutionOptions] = None
                                          ) -> Optional[Path]:
        """Execute test cases from Test Plan or Test Suite.

        Args:
            testcases: List of TestCase objects (no duplicates)
            exec_id: ID of the Test Plan or Test Suite
            options: Execution options (prefix, flatten_result, robot_args).
                     Defaults to ExecutionOptions() when None.

        Returns:
            Path to the folder containing the results, or None when list is empty.
        """
        if options is None:
            options = ExecutionOptions()

        if not testcases:
            logger.info("List of test case is empty!")
            return None

        len_tc_list = len(testcases)
        logger.info("="*80)
        logger.info("Starting sequential execution of %d test cases from %s %s",
                    len_tc_list, options.prefix, exec_id)
        logger.info("="*80)

        execution_folder = self.output_directory / f"{options.prefix}_{exec_id}"
        execution_folder.mkdir(parents=True, exist_ok=True)
        logger.info("Execution folder: %s", execution_folder)

        self._resolve_paths_for_testcases(
            testcases, Path(self.config.get('workspace', {}).get('path', '.'))
        )

        groups = self._group_testcases_by_file(testcases)
        logger.info("Grouped %d test case(s) into %d robot file groups",
                    len_tc_list, len(groups))

        for group_idx, group in enumerate(groups.values(), start=1):
            robot_file = group['file']
            group_tcs = group['testcases']
            logger.info("-"*80)
            logger.info("Executing group %d/%d: %s (%d test case(s))",
                        group_idx, len(groups), robot_file.name, len(group_tcs))
            for tc in group_tcs:
                logger.info("  TC ID: %s - TC Name: %s", tc.tcid, tc.test_name)
            logger.info("-"*80)

            group_output_folder = execution_folder / self._sanitize_filename(
                f"group_{group_idx:03d}_{robot_file.stem}"
            )

            try:
                self._execute_testcase_group(robot_file, group_tcs,
                                             group_output_folder, options.robot_args)
            except RuntimeError as e:
                logger.error("Failed to execute group %s: %s", robot_file.name, str(e))
                for tc in group_tcs:
                    tc.mark_as_error(f"Execution error: {str(e)}")

            for tc in group_tcs:
                logger.info("  TC ID: %s - Status: %s, Time: %.2fs",
                            tc.tcid, tc.status, tc.execution_time)
                if tc.error_message:
                    logger.info("  Error: %s", tc.error_message)

        self._post_process_results(testcases, execution_folder,
                                   f"{options.prefix}_{exec_id}", options.flatten_result)

        logger.info("="*80)
        logger.info("Sequential execution completed")
        logger.info("="*80)
        self._log_execution_summary(testcases, len_tc_list)

        return execution_folder

    # ------------------------------------------------------------------
    # Group execution helpers
    # ------------------------------------------------------------------

    def _build_robot_cmd(self, robot_file: Path, output_folder: Path,
                         testcases: List[TestCase],
                         robot_args: Optional[str]) -> Tuple[List[str], List[TestCase]]:
        """Build the robot command and return (cmd, valid_testcases).

        Test cases that do not exist in the robot file are marked as error
        and excluded from valid_testcases.
        """
        cmd = [
            sys.executable, '-m', self.robot_executable,
            '--outputdir', str(output_folder),
            '--output', 'output.xml',
            '--log', 'log.html',
            '--report', 'report.html',
        ]

        valid_testcases = []
        for tc in testcases:
            if self._check_testcase_exists(robot_file, tc.test_name):
                cmd.extend(['--test', tc.test_name])
                valid_testcases.append(tc)
            else:
                error_msg = f"Missing Test Case '{tc.test_name}' in '{robot_file}'"
                logger.error(error_msg)
                tc.mark_as_error(error_msg)

        cmd.extend(self.custom_args)
        if robot_args:
            cmd.extend(shlex.split(robot_args))
        cmd.extend(self.additional_args)
        cmd.append(str(robot_file))

        return cmd, valid_testcases

    def _execute_testcase_group(self, robot_file: Path,
                                testcases: List[TestCase],
                                group_output_folder: Path,
                                robot_args: Optional[str] = None):
        """Execute a group of test cases sharing the same .robot file.

        Args:
            robot_file: Path to the shared .robot file
            testcases: TestCase objects in this group
            group_output_folder: Pre-computed output folder for this group
            robot_args: Additional Robot Framework arguments
        """
        group_output_folder.mkdir(parents=True, exist_ok=True)

        for tc in testcases:
            tc.mark_as_running()

        cmd, valid_testcases = self._build_robot_cmd(robot_file, group_output_folder,
                                                     testcases, robot_args)
        logger.info("robot cmd: [%s]", ' '.join(cmd))

        output_xml = group_output_folder / "output.xml"
        log_html = group_output_folder / "log.html"
        report_html = group_output_folder / "report.html"

        try:
            logger.debug("Executing command: %s", ' '.join(cmd))
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.execution_config.get('test_timeout_seconds', 300) * len(testcases),
                check=True
            )
            logger.debug("Robot return code: %d", result.returncode)

            for tc in valid_testcases:
                tc.set_output_xml_path(output_xml if output_xml.exists() else None)
                tc.set_log_html_path(log_html if log_html.exists() else None)
                tc.set_report_html_path(report_html if report_html.exists() else None)

            if output_xml.exists():
                for tc in valid_testcases:
                    self._parse_and_update_status(tc, output_xml)
            else:
                error_msg = f"No output.xml generated. STDERR: {result.stderr}"
                for tc in valid_testcases:
                    tc.mark_as_error(error_msg)

        except subprocess.TimeoutExpired:
            timeout_limit = self.execution_config.get('test_timeout_seconds', 300)
            error_msg = f"Test execution timeout after {timeout_limit * len(valid_testcases)}s"
            logger.error(error_msg)
            for tc in valid_testcases:
                tc.mark_as_error(error_msg)

        except RuntimeError as e:
            error_msg = f"Execution error: {str(e)}"
            logger.error(error_msg)
            for tc in valid_testcases:
                tc.mark_as_error(error_msg)

    def _execute_single_testcase(self,
                                 testcase: TestCase,
                                 execution_folder: Path,
                                 robot_args: str = None):
        """
        Execute a single test case

        Args:
            testcase: TestCase object to execute
            execution_folder: Parent folder for all executions
            robot_args: Additional Robot Framework arguments
        """
        robot_file = testcase.test_script_path
        if not robot_file or not robot_file.exists():
            error_msg = f"Robot file not found: {robot_file}"
            logger.error(error_msg)
            testcase.mark_as_error(error_msg)
            return

        tc_folder_name = self._sanitize_filename(f"{testcase.tcid}_{testcase.test_name}")
        tc_output_folder = execution_folder / tc_folder_name
        tc_output_folder.mkdir(parents=True, exist_ok=True)

        testcase.mark_as_running()

        cmd = [
            sys.executable, '-m',
            self.robot_executable,
            '--outputdir', str(tc_output_folder),
            '--output', 'output.xml',
            '--log', 'log.html',
            '--report', 'report.html',
            '--test', testcase.test_name
        ]
        cmd.extend(self.custom_args)
        if robot_args:
            cmd.extend(shlex.split(robot_args))
        cmd.extend(self.additional_args)
        cmd.append(str(robot_file))

        logger.info("robot cmd: [%s]", ' '.join(cmd))

        try:
            logger.debug("Executing command: [%s]", ' '.join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.execution_config.get('test_timeout_seconds', 300),
                check=True
            )
            logger.debug("Robot return code: %d", result.returncode)

            output_xml = tc_output_folder / "output.xml"
            log_html = tc_output_folder / "log.html"
            report_html = tc_output_folder / "report.html"

            testcase.set_output_xml_path(output_xml if output_xml.exists() else None)
            testcase.set_log_html_path(log_html if log_html.exists() else None)
            testcase.set_report_html_path(report_html if report_html.exists() else None)

            if output_xml.exists():
                self._parse_and_update_status(testcase, output_xml)
            else:
                testcase.mark_as_error(f"No output.xml generated. STDERR: {result.stderr}")

        except subprocess.TimeoutExpired:
            time_out = self.execution_config.get('test_timeout_seconds', 300)
            error_msg = f"Test execution timeout after {time_out}s"
            logger.error(error_msg)
            testcase.mark_as_error(error_msg)

        except RuntimeError as e:
            error_msg = f"Execution error: {str(e)}"
            logger.error(error_msg)
            testcase.mark_as_error(error_msg)

    # ------------------------------------------------------------------
    # Status parsing helpers
    # ------------------------------------------------------------------

    def _apply_robot_status(self, testcase: TestCase, status_elem) -> None:
        """Map PASS/FAIL/SKIP from a Robot XML status element onto testcase."""
        status = status_elem.get('status', 'FAIL')
        if status == 'PASS':
            testcase.mark_as_passed()
        elif status == 'FAIL':
            testcase.mark_as_failed(status_elem.text or "Test failed")
        elif status == 'SKIP':
            testcase.mark_as_skipped(status_elem.text or "Test skipped")
        else:
            testcase.mark_as_error(f"Unknown status: {status}")

    def _apply_timing_from_status(self, testcase: TestCase, status_elem) -> None:
        """Parse Robot Framework timestamps from status element and store on testcase."""
        start_str = status_elem.get('starttime')
        end_str = status_elem.get('endtime')
        if not (start_str and end_str):
            return
        try:
            start_dt = datetime.strptime(start_str, '%Y%m%d %H:%M:%S.%f')
            end_dt = datetime.strptime(end_str, '%Y%m%d %H:%M:%S.%f')
            testcase.start_time = start_dt
            testcase.end_time = end_dt
            testcase.execution_time = (end_dt - start_dt).total_seconds()
        except ValueError:
            pass

    def _parse_and_update_status(self, testcase: TestCase, output_xml: Path):
        """
        Parse output.xml and update test case status

        Args:
            testcase: TestCase object to update
            output_xml: Path to output.xml file
        """
        try:
            root = ET.parse(output_xml).getroot()

            test_elem = next(
                (t for t in root.findall('.//test') if t.get('name') == testcase.test_name),
                root.find('.//test')
            )

            if test_elem is None:
                testcase.mark_as_error("No test element found in output.xml")
                return

            status_elem = test_elem.find('status')
            if status_elem is None:
                testcase.mark_as_error("No status element found in output.xml")
                return

            self._apply_robot_status(testcase, status_elem)
            self._apply_timing_from_status(testcase, status_elem)

        except ET.ParseError as e:
            logger.error("Failed to parse output.xml: %s", str(e))
            testcase.mark_as_error(f"Failed to parse output.xml: {str(e)}")

        except IOError as e:
            logger.error("Error parsing results: %s", str(e))
            testcase.mark_as_error(f"Error parsing results: {str(e)}")

    # ------------------------------------------------------------------
    # Post-processing helpers
    # ------------------------------------------------------------------

    def _collect_valid_xmls(self, testcases: List[TestCase]) -> List[str]:
        """Collect unique, existing output.xml paths from testcases."""
        seen: set = set()
        result = []
        for tc in testcases:
            xml_path = tc.output_xml_path
            if xml_path and xml_path.exists() and str(xml_path) not in seen:
                result.append(str(xml_path))
                seen.add(str(xml_path))
        return result

    def _aggregate_suite_data(self, merged_result) -> Tuple[list, dict, list, list]:
        """Traverse sub-suites and aggregate tests, combined metadata, and timing.

        When ExecutionResult is built from multiple XMLs, Robot Framework wraps them
        under a synthetic root suite whose .suites contains one entry per XML.
        When only a single XML is provided, the root suite IS that XML's suite directly
        and .suites is empty — so we fall back to treating the root suite itself as the
        sole source.
        """
        all_tests: list = []
        combined_metadata: dict = {}
        start_times: list = []
        end_times: list = []

        suites_to_process = (merged_result.suite.suites
                             if merged_result.suite.suites
                             else [merged_result.suite])

        for sub_suite in suites_to_process:
            for key, value in sub_suite.metadata.items():
                if key in combined_metadata:
                    current = [v.strip() for v in str(combined_metadata[key]).split(',')]
                    if str(value) not in current:
                        combined_metadata[key] = f"{combined_metadata[key]}, {value}"
                else:
                    combined_metadata[key] = value

            for test in sub_suite.tests:
                if test.starttime:
                    start_times.append(test.starttime)
                if test.endtime:
                    end_times.append(test.endtime)
                source_info = f"Source: {sub_suite.source}"
                test.doc = f"{test.doc}\n\n{source_info}" if test.doc else source_info
                all_tests.append(test)

        return all_tests, combined_metadata, start_times, end_times

    def _run_rebot(self, execution_folder: Path, report_name: str,
                   main_output_xml: Path) -> None:
        """Generate HTML log and report via rebot."""
        rebot_cmd = [
            sys.executable, '-m', self.rebot_executable,
            '--outputdir', str(execution_folder),
            '--name', report_name,
            '--log', 'log.html',
            '--report', 'report.html',
            str(main_output_xml)
        ]
        logger.info("rebot cmd: [%s]", ' '.join(rebot_cmd))
        subprocess.run(rebot_cmd, check=True, capture_output=True)

    def _post_process_results(self,
                              testcases: List[TestCase],
                              execution_folder: Path,
                              report_name: str,
                              flatten: bool = True):
        """
        Post-process results: Combine XMLs, merge metadata, and optionally flatten suites.

        Args:
            testcases: List of executed TestCase objects
            execution_folder: Folder containing the results
            report_name: Name used for the merged report (e.g. "TP_12345")
            flatten: If True, moves all tests to root suite. If False, keeps sub-suites.
        """
        if not testcases:
            return

        valid_xmls = self._collect_valid_xmls(testcases)
        if not valid_xmls:
            logger.warning("No output.xml files found.")
            return

        main_output_xml = execution_folder / "output.xml"

        try:
            merged_result = ExecutionResult(*valid_xmls)
            merged_result.suite.name = report_name

            all_tests, combined_metadata, start_times, end_times = \
                self._aggregate_suite_data(merged_result)

            merged_result.suite.metadata = combined_metadata

            if flatten:
                logger.info("Flattening results for %s", report_name)
                all_tests.sort(key=lambda t: t.starttime if t.starttime else "")
                merged_result.suite.tests = all_tests
                merged_result.suite.suites = []
            else:
                logger.info("Keeping nested suite structure for %s", report_name)

            if start_times:
                merged_result.suite.starttime = min(start_times)
            if end_times:
                merged_result.suite.endtime = max(end_times)

            merged_result.save(main_output_xml)
            self._run_rebot(execution_folder, report_name, main_output_xml)

        except RuntimeError as e:
            logger.error("Error during result processing: %s", str(e))

        self._archive_individual_logs(testcases, execution_folder)

    def _archive_individual_logs(self, testcases: List[TestCase], execution_folder: Path) -> None:
        """Archive individual log files for each test case into a structured directory.

        Args:
            testcases (List[TestCase]): List of test case objects
            execution_folder (Path): Folder containing the results
        """
        logs_dir = execution_folder / "logs"
        logs_dir.mkdir(exist_ok=True)
        for tc in testcases:
            xml_path = tc.output_xml_path
            if xml_path and xml_path.parent.exists() and xml_path.parent != execution_folder:
                folder = xml_path.parent
                shutil.make_archive(str(logs_dir / folder.name), 'zip', folder)
                shutil.rmtree(folder)

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by removing invalid characters

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        max_length = 200
        if len(filename) > max_length:
            filename = filename[:max_length]

        return filename
