using System.Diagnostics;
using ProofAgent.Coq;
using Xunit;

namespace ProofAgent.Tests;

public class ProcessRunnerTests
{
    [Fact]
    public async Task RunProcessAsync_WhenCancellationRequested_ThrowsOperationCanceledException()
    {
        var runner = new ProcessRunner();
        using var cancellationSource = new CancellationTokenSource();
        var psi = _CreateSleepProcessStartInfo(seconds: 60);

        cancellationSource.CancelAfter(TimeSpan.FromMilliseconds(80));

        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            runner.RunProcessAsync(psi, TimeSpan.FromSeconds(120), cancellationSource.Token));
    }

    [Fact]
    public async Task RunProcessAsync_WhenProcessExceedsTimeout_ReturnsTimedOutWithoutCancellation()
    {
        var runner = new ProcessRunner();
        var psi = _CreateSleepProcessStartInfo(seconds: 30);

        var result = await runner.RunProcessAsync(
            psi,
            TimeSpan.FromMilliseconds(80),
            CancellationToken.None);

        Assert.True(result.TimedOut);
    }

    private static ProcessStartInfo _CreateSleepProcessStartInfo(int seconds)
    {
        var psi = new ProcessStartInfo
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        if (OperatingSystem.IsWindows())
        {
            psi.FileName = "cmd.exe";
            psi.ArgumentList.Add("/c");
            psi.ArgumentList.Add("timeout /t " + seconds);
            return psi;
        }

        psi.FileName = "/bin/sleep";
        psi.ArgumentList.Add(seconds.ToString());
        return psi;
    }
}
