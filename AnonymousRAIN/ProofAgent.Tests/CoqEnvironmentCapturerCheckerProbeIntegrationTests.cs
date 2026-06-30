using ProofAgent.Agent;
using ProofAgent.Coq;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

/// <summary>
/// Integration tests for <see cref="CoqEnvironmentCapturer"/> environment-before-error capture via reflection, using <see cref="CoqChecker"/> and a <c>coqc</c> check command.
/// Set environment variable <c>RUN_COQ_ENV_CHECKER_INTEGRATION_TESTS=1</c> and ensure <c>coqc</c> is on PATH to run.
/// </summary>
public class CoqEnvironmentCapturerCheckerProbeIntegrationTests
{
    private static bool _ShouldRunCheckerIntegration()
    {
        var flag = Environment.GetEnvironmentVariable("RUN_COQ_ENV_CHECKER_INTEGRATION_TESTS");
        if (!string.Equals(flag, "1", StringComparison.Ordinal))
        {
            return false;
        }

        return _IsCoqcOnPath();
    }

    private static bool _IsCoqcOnPath()
    {
        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        {
            if (string.IsNullOrEmpty(dir))
            {
                continue;
            }

            var candidate = Path.Combine(dir.Trim(), OperatingSystem.IsWindows() ? "coqc.exe" : "coqc");
            if (File.Exists(candidate))
            {
                return true;
            }
        }

        return false;
    }

    private static async Task<CoqEnvironment> _InvokeGetEnvironmentTextAsync(
        CoqEnvironmentCapturer capturer,
        CoqError error,
        CancellationToken cancellationToken)
    {
        var taskObject = ReflectionTestAccess.InvokeInstanceNonPublic(
            capturer,
            "_GetEnvironmentTextAsync",
            new object?[] { error, cancellationToken, null });
        var task = (Task<CoqEnvironment>)taskObject!;
        return await task.ConfigureAwait(false);
    }

    [Fact]
    public async Task GetEnvironmentBeforeErrorAsync_StringWithDotSpaceInGoal_IsCaptured()
    {
        if (!_ShouldRunCheckerIntegration())
        {
            return;
        }

        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCheckerEnv_" + Guid.NewGuid().ToString("N", null));
        Directory.CreateDirectory(root);
        try
        {
            const string coqSource = """
                Require Import String.
                Open Scope string_scope.

                Lemma dot_in_goal : "a. b" = "a. b".
                Proof.
                  idtac.
                  apply True.
                Qed.

                """;
            File.WriteAllText(Path.Combine(root, "DotSpace.v"), coqSource);

            var logger = TestInjectedLogger.CreateFatalOnly();
            var fileSystem = new ProjectFileSystem(root);
            var checker = new CoqChecker(
                logger,
                new ProcessRunner(),
                fileSystem.Root,
                new CoqProofSkipFinder(fileSystem));
            var sentenceSplitter = new LineCoqSentenceSplitterTests(fileSystem);
            var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
            var capturer = new CoqEnvironmentCapturer(
                fileSystem,
                checker,
                sentenceAnalyzer,
                120,
                "coqc -q DotSpace.v",
                logger);
            var err = PathTests.Error("DotSpace.v", 7, 0, "Error: Cannot apply lemma True.", root);
            var env = await _InvokeGetEnvironmentTextAsync(capturer, err, CancellationToken.None);

            Assert.Contains("a. b", env.RawText, StringComparison.Ordinal);
            Assert.Contains("============================", env.RawText, StringComparison.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(root, true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public async Task GetEnvironmentBeforeErrorAsync_MultiSubgoalAfterInduction_ShowsNumberedGoalsWhenPresent()
    {
        if (!_ShouldRunCheckerIntegration())
        {
            return;
        }

        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCheckerMulti_" + Guid.NewGuid().ToString("N", null));
        Directory.CreateDirectory(root);
        try
        {
            const string coqSource = """
                Lemma add_assoc n m p : n + (m + p) = n + m + p.
                Proof.
                  induction n; simpl.
                  - reflexivity.
                  - f_equal; assumption.
                Qed.

                """;
            File.WriteAllText(Path.Combine(root, "Multi.v"), coqSource);

            var logger = TestInjectedLogger.CreateFatalOnly();
            var fileSystem = new ProjectFileSystem(root);
            var checker = new CoqChecker(
                logger,
                new ProcessRunner(),
                fileSystem.Root,
                new CoqProofSkipFinder(fileSystem));
            var sentenceSplitter = new LineCoqSentenceSplitterTests(fileSystem);
            var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
            var capturer = new CoqEnvironmentCapturer(
                fileSystem,
                checker,
                sentenceAnalyzer,
                120,
                "coqc -q Multi.v",
                logger);
            var err = PathTests.Error("Multi.v", 6, 0, "Error: synthetic", root);
            var env = await _InvokeGetEnvironmentTextAsync(capturer, err, CancellationToken.None);

            if (env.RawText.Contains("goal 2:", StringComparison.Ordinal))
            {
                Assert.Contains("goal 1:", env.RawText, StringComparison.Ordinal);
            }
        }
        finally
        {
            try
            {
                Directory.Delete(root, true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public async Task GetEnvironmentBeforeErrorAsync_SubgoalDischargedThenNextTacticFails_CapturesEnvironment()
    {
        if (!_ShouldRunCheckerIntegration())
        {
            return;
        }

        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCheckerSubgoal_" + Guid.NewGuid().ToString("N", null));
        Directory.CreateDirectory(root);
        try
        {
            const string coqSource = """
                Lemma helper : True.
                Proof. exact I. Qed.

                Lemma main : True /\ True.
                Proof.
                  split.
                  +
                    exact I.
                  +
                    exact I.
                  apply True.
                Qed.

                """;
            File.WriteAllText(Path.Combine(root, "Subgoal.v"), coqSource);

            var logger = TestInjectedLogger.CreateFatalOnly();
            var fileSystem = new ProjectFileSystem(root);
            var checker = new CoqChecker(
                logger,
                new ProcessRunner(),
                fileSystem.Root,
                new CoqProofSkipFinder(fileSystem));
            var sentenceSplitter = new LineCoqSentenceSplitterTests(fileSystem);
            var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
            var capturer = new CoqEnvironmentCapturer(
                fileSystem,
                checker,
                sentenceAnalyzer,
                120,
                "coqc -q Subgoal.v",
                logger);
            var err = PathTests.Error("Subgoal.v", 11, 0, "Error: No such goal.", root);
            var env = await _InvokeGetEnvironmentTextAsync(capturer, err, CancellationToken.None);

            Assert.False(string.IsNullOrWhiteSpace(env.RawText));
            Assert.DoesNotContain("__IMPOSSIBLEE_TOO_COLLIDEE___", env.RawText, StringComparison.Ordinal);
            Assert.True(
                env.RawText.Contains("============================", StringComparison.Ordinal)
                || env.RawText.Contains("No more goals", StringComparison.Ordinal),
                "Expected Show output with goals or 'No more goals.'");
        }
        finally
        {
            try
            {
                Directory.Delete(root, true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public async Task GetEnvironmentBeforeErrorAsync_NestedCoqProject_CheckerRunsFromWorkspaceRoot()
    {
        if (!_ShouldRunCheckerIntegration())
        {
            return;
        }

        var workspaceRoot = Path.Combine(Path.GetTempPath(), "ProofAgentCheckerNest_" + Guid.NewGuid().ToString("N", null));
        var inner = Path.Combine(workspaceRoot, "pkg", "inner");
        Directory.CreateDirectory(inner);
        try
        {
            File.WriteAllText(Path.Combine(inner, "_CoqProject"), "");
            const string coqSource = """
                Require Import String.
                Open Scope string_scope.

                Lemma dot_in_goal : "a. b" = "a. b".
                Proof.
                  idtac.
                  apply True.
                Qed.

                """;
            File.WriteAllText(Path.Combine(inner, "Inner.v"), coqSource);

            var logger = TestInjectedLogger.CreateFatalOnly();
            var fileSystem = new ProjectFileSystem(workspaceRoot);
            var checker = new CoqChecker(
                logger,
                new ProcessRunner(),
                fileSystem.Root,
                new CoqProofSkipFinder(fileSystem));
            var sentenceSplitter = new LineCoqSentenceSplitterTests(fileSystem);
            var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
            var capturer = new CoqEnvironmentCapturer(
                fileSystem,
                checker,
                sentenceAnalyzer,
                120,
                "coqc -q pkg/inner/Inner.v",
                logger);
            var err = PathTests.Error("pkg/inner/Inner.v", 7, 0, "Error: Cannot apply lemma True.", workspaceRoot);
            var env = await _InvokeGetEnvironmentTextAsync(capturer, err, CancellationToken.None);

            Assert.Contains("a. b", env.RawText, StringComparison.Ordinal);
            Assert.Contains("============================", env.RawText, StringComparison.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(workspaceRoot, true);
            }
            catch
            {
                // best-effort
            }
        }
    }
}
