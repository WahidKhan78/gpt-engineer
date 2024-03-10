"""
Module for running benchmarks.

This module defines functions to run benchmarks using a given agent and to print
the results of the benchmark tasks.

Functions
---------
run : function
    Runs the benchmark tasks using the provided agent and returns a list of TaskResult objects.

print_results : function
    Prints the results of the benchmark tasks to the console.
"""
import subprocess
import time

from typing import List, Optional

from gpt_engineer.benchmark.types import Assertable, Benchmark, TaskResult
from gpt_engineer.core.base_agent import BaseAgent
from gpt_engineer.core.chat_to_files import DiffError
from gpt_engineer.core.default.disk_execution_env import DiskExecutionEnv


def run(
    agent: BaseAgent,
    benchmark: Benchmark,
    task_name: Optional[str] = None,
    verbose=False,
) -> List[TaskResult]:
    """
    Runs the benchmark tasks using the provided agent and returns a list of TaskResult objects.

    Parameters
    ----------
    agent : BaseAgent
        The agent to use for running the benchmark tasks.
    benchmark : Benchmark
        The benchmark containing the tasks to run.
    task_name : Optional[str], default=None
        An optional name of a specific task to run within the benchmark.
    verbose : bool, default=False
        A flag to indicate whether to print verbose output during the benchmark.

    Returns
    -------
    List[TaskResult]
        A list of TaskResult objects representing the results of the benchmark tasks.
    """
    task_results = []
    for task in benchmark.tasks:
        print(f'--> Running task: {task.name}\n')
        if task.inputs is not None and task.assertions is not None:
            assert len(task.inputs) == len(task.assertions)

        t0 = time.time()
        try:
            files_dict = agent.improve(task.initial_code, task.prompt)
        except DiffError as e:  # Temporary catch errors related to git diffs
            print(e)
            continue
        t1 = time.time()

        try:
            exec_results = run_and_get_result(files_dict, task, benchmark)
        except subprocess.TimeoutExpired as e:
            print(e)
            continue

        task_results.append(
            TaskResult(
                task_name=task.name,
                assertion_results=[
                    {
                        key: assertion(exec_results[i])
                        for key, assertion in task.assertions[i].items()
                    }
                    for i in range(len(task.assertions))
                ],
                duration=t1 - t0,
            )
        )

        if verbose:
            print_results(task_results)
    return task_results


def run_and_get_result(files_dict, task, benchmark) -> List[Assertable]:
    env = DiskExecutionEnv()
    env.upload(files_dict)

    exec_results = []
    if task.command:
        for i, input_pars in enumerate(task.inputs or [""]):
            print(i, input_pars)
            p = env.popen(task.command + ' "' + input_pars + '"')
            stdout, stderr = p.communicate(timeout=benchmark.timeout)
            stdout, stderr = stdout.decode("utf-8"), stderr.decode("utf-8")
            exec_results.append(
                Assertable(
                    files=files_dict,
                    env=env,
                    process=p,
                    stdout=stdout,
                    stderr=stderr,
                )
            )
    else:
        exec_results.append(
            Assertable(
                files=files_dict,
                env=env,
                process=None,
                stdout=None,
                stderr=None,
            )
        )

    return exec_results


def print_results(results: list[TaskResult]):
    """
    Prints the results of the benchmark tasks to the console.

    Parameters
    ----------
    results : list[TaskResult]
        A list of TaskResult objects representing the results of the benchmark tasks.

    Returns
    -------
    None
    """
    for task_result in results:
        print(f"\n--- Results for {task_result.task_name} ---")
        print(f"{task_result.task_name} ({task_result.duration:.2f}s)")
        for assertion_results_dict in task_result.assertion_results:
            for assertion_name, assertion_result in assertion_results_dict.items():
                checkmark = "✅" if assertion_result else "❌"
                print(f"  {checkmark} {assertion_name}")
            print()
        print()

    success_rates = [task_result.success_rate for task_result in results]
    avg_success_rate = sum(success_rates) / len(results)

    total_time = sum(task_result.duration for task_result in results)

    correct_assertions = sum(
        sum(
            assertion_result
            for assertion_results_dict in task_result.assertion_results
            for assertion_result in assertion_results_dict.values()
        )
        for task_result in results
    )
    total_assertions = sum(
        len(assertion_results_dict) for task_result in results
        for assertion_results_dict in task_result.assertion_results
    )
    correct_tasks = [task_result for task_result in results if task_result.success_rate == 1]

    print("--- Results ---")
    print(f"Total time: {total_time:.2f}s")
    print(f"Completely correct tasks: {len(correct_tasks)}/{len(results)}")
    print(f"Total correct assertions: {correct_assertions}/{total_assertions}")
    print(f"Average success rate: {avg_success_rate * 100}% on {len(results)} tasks")
    print("--- Results ---")
    print()
