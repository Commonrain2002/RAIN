using System.Diagnostics;
using System.Text;

namespace ProofAgent.Coq;

public record ProcessRunResult(int ExitCode, string CombinedOutput, bool TimedOut);

/// <summary>Runs external processes with captured stdout/stderr and optional timeout.</summary>
public class ProcessRunner
{
    public async Task<ProcessRunResult> RunProcessAsync(
        ProcessStartInfo psi,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();

        _AddCallbacks(process, stdout, stderr);

        if (!process.Start())
        {
            throw new InvalidOperationException("Failed to start process: " + psi.FileName);
        }

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        try
        {
            var waitOutcome = await _WaitForExitOrTimeoutAsync(
                    process,
                    timeout,
                    stdout,
                    stderr,
                    cancellationToken)
                .ConfigureAwait(false);
            if (waitOutcome.TimedOut)
            {
                return waitOutcome.TimeoutResult!;
            }
        }
        catch (OperationCanceledException)
        {
            _KillProcessBestEffort(process);

            throw;
        }

        return new ProcessRunResult(
            process.ExitCode,
            _CombineStdoutStderr(stdout, stderr),
            false);
    }

    #region Private Methods

    private static void _AddCallbacks(Process process, StringBuilder stdout, StringBuilder stderr)
    {
        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data != null)
            {
                stdout.AppendLine(e.Data);
            }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data != null)
            {
                stderr.AppendLine(e.Data);
            }
        };
    }

    private static async Task<ProcessExitWaitOutcome> _WaitForExitOrTimeoutAsync(
        Process process,
        TimeSpan timeout,
        StringBuilder stdout,
        StringBuilder stderr,
        CancellationToken cancellationToken)
    {
        var exitTask = process.WaitForExitAsync(cancellationToken);
        var timeoutTask = Task.Delay(timeout, cancellationToken);
        var completedTask = await Task.WhenAny(exitTask, timeoutTask).ConfigureAwait(false);
        if (cancellationToken.IsCancellationRequested)
        {
            _KillProcessBestEffort(process);
            cancellationToken.ThrowIfCancellationRequested();
        }

        if (completedTask == timeoutTask)
        {
            _KillProcessBestEffort(process);

            return new ProcessExitWaitOutcome
            {
                TimedOut = true,
                TimeoutResult = new ProcessRunResult(
                    -1,
                    _CombineStdoutStderr(stdout, stderr),
                    true),
            };
        }

        await exitTask.ConfigureAwait(false);

        return new ProcessExitWaitOutcome
        {
            TimedOut = false,
            TimeoutResult = null,
        };
    }

    private static void _KillProcessBestEffort(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
        }
        catch
        {
            // best-effort
        }
    }

    private static string _CombineStdoutStderr(StringBuilder stdout, StringBuilder stderr)
    {
        var combined = stdout.ToString();
        var err = stderr.ToString();
        if (!string.IsNullOrWhiteSpace(err))
        {
            combined = string.IsNullOrWhiteSpace(combined) ? err : combined + Environment.NewLine + err;
        }

        return combined;
    }

    #endregion Private Methods

    private class ProcessExitWaitOutcome
    {
        public bool TimedOut { get; init; }

        public ProcessRunResult? TimeoutResult { get; init; }
    }
}
