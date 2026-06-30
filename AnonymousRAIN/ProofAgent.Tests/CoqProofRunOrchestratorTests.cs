using System.Text.Json;
using ProofAgent.Agent;
using ProofAgent.Coq;
using ProofAgent.Llm;
using ProofAgent.Session;
using ProofAgent.Tests.Fakes;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class CoqProofRunOrchestratorTests
{
    private const int _CheckTimeoutSeconds = 30;

    private const string _ExpectedEarlySuccessAssistantText =
        "Proof check passed before proof session. Proof session was skipped.";

    [Fact]
    public async Task RunAsync_ProofFirstTurn_IncludesKnowledgeCollectionAssistantText()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var proofSession = new RecordingLlmSession(new LlmChat("proof draft"));
            var initialError = PathTests.Error("T.v", 2, 0, "type mismatch", root);
            var initialFailure = new CoqCheck(CoqCheckType.Failed, initialError, "raw", _CheckTimeoutSeconds);
            var finalSuccess = new CoqCheck(CoqCheckType.Success, null, "", _CheckTimeoutSeconds);
            var projectChecker = new QueueCoqProjectChecker(
                new[]
                {
                    initialFailure,
                    finalSuccess,
                });
            var multiErrorChecker = _CreateMultiErrorChecker(
                logger,
                root,
                targetCoqFileRelativePath,
                projectChecker,
                environmentText: "(plus_comm),   ignored");
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                proofSession,
                multiErrorChecker,
                "Prove T.",
                new Dictionary<string, IReadOnlyList<CoqSentence>>
                {
                    ["Knowledge.v"] = new[]
                    {
                        _Sentence(CoqSentenceVernacType.Definition, "plus_comm", 1, 1, "Definition plus_comm := True."),
                    },
                });

            var result = await proofRunOrchestrator.RunAsync(CancellationToken.None);

            Assert.True(result.Success);
            Assert.Null(result.LastError);
            Assert.Equal("proof draft", result.LastAssistantText);
            Assert.NotNull(proofSession.LastUserMessage);
            Assert.Contains("Prove T.", proofSession.LastUserMessage, StringComparison.Ordinal);
            Assert.Contains("## Definitions helpful for the proof", proofSession.LastUserMessage, StringComparison.Ordinal);
            Assert.Contains("Knowledge.v:1-1", proofSession.LastUserMessage, StringComparison.Ordinal);
            Assert.Contains("Definition plus_comm := True.", proofSession.LastUserMessage, StringComparison.Ordinal);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    [Fact]
    public async Task RunAsync_WhenRequireImportsSsreflect_IncludesSsreflectGuidanceInFirstUserMessage()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var proofSession = new RecordingLlmSession(new LlmChat("proof draft"));
            var initialError = PathTests.Error("T.v", 2, 0, "type mismatch", root);
            var initialFailure = new CoqCheck(CoqCheckType.Failed, initialError, "raw", _CheckTimeoutSeconds);
            var finalSuccess = new CoqCheck(CoqCheckType.Success, null, "", _CheckTimeoutSeconds);
            var projectChecker = new QueueCoqProjectChecker(new[] { initialFailure, finalSuccess });
            var multiErrorChecker = _CreateMultiErrorChecker(
                logger,
                root,
                targetCoqFileRelativePath,
                projectChecker,
                environmentText: "env");
            var requireSentence = new CoqSentence
            {
                VernacType = CoqSentenceVernacType.Require,
                Text = "From mathcomp Require Import ssreflect.",
                Tokens = new List<string> { "From", "mathcomp", "Require", "Import", "ssreflect" },
            };
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                proofSession,
                multiErrorChecker,
                "Prove T.",
                new Dictionary<string, IReadOnlyList<CoqSentence>>
                {
                    ["Imports.v"] = new[] { requireSentence },
                });

            await proofRunOrchestrator.RunAsync(CancellationToken.None);

            Assert.NotNull(proofSession.LastUserMessage);
            Assert.Contains("## SSReflect syntax and semantics", proofSession.LastUserMessage, StringComparison.Ordinal);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    [Fact]
    public async Task RunAsync_WhenFinalMultiErrorCheckSucceeds_ReturnsSuccess()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var proofSession = new RecordingLlmSession(new LlmChat("final proof text"));
            var projectChecker = new QueueCoqProjectChecker(
                new[]
                {
                    new CoqCheck(CoqCheckType.Success, null, "", _CheckTimeoutSeconds),
                });
            var multiErrorChecker = _CreateMultiErrorChecker(logger, root, targetCoqFileRelativePath, projectChecker);
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                proofSession,
                multiErrorChecker,
                "Goal.");

            var result = await proofRunOrchestrator.RunAsync(CancellationToken.None);

            Assert.True(result.Success);
            Assert.Null(result.LastError);
            Assert.Equal(_ExpectedEarlySuccessAssistantText, result.LastAssistantText);
            Assert.Null(proofSession.LastUserMessage);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    [Fact]
    public async Task RunAsync_WhenFinalMultiErrorCheckFails_ReturnsFailureWithLastError()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var initialError = PathTests.Error("T.v", 2, 0, "type mismatch", root);
            var finalError = PathTests.Error("T.v", 3, 0, "still wrong", root);
            var initialFailedCheck = new CoqCheck(CoqCheckType.Failed, initialError, "raw coqc output", _CheckTimeoutSeconds);
            var finalFailedCheck = new CoqCheck(CoqCheckType.Failed, finalError, "raw coqc output", _CheckTimeoutSeconds);
            var projectChecker = new QueueCoqProjectChecker(new[] { initialFailedCheck, finalFailedCheck });
            var multiErrorChecker = _CreateMultiErrorChecker(
                logger,
                root,
                targetCoqFileRelativePath,
                projectChecker,
                extraErrorCount: 0);
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                new RecordingLlmSession(new LlmChat("draft with error")),
                multiErrorChecker,
                "Goal.");

            var result = await proofRunOrchestrator.RunAsync(CancellationToken.None);

            Assert.False(result.Success);
            Assert.Same(finalError, result.LastError);
            Assert.Equal("draft with error", result.LastAssistantText);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    [Fact]
    public async Task RunAsync_WhenFinalMultiErrorCheckTimesOut_ReturnsFailureWithoutLastError()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var initialError = PathTests.Error("T.v", 2, 0, "type mismatch", root);
            var initialFailedCheck = new CoqCheck(CoqCheckType.Failed, initialError, "raw", _CheckTimeoutSeconds);
            var timedOutCheck = new CoqCheck(CoqCheckType.TimedOut, null, "hang", _CheckTimeoutSeconds);
            var projectChecker = new QueueCoqProjectChecker(new[] { initialFailedCheck, timedOutCheck });
            var multiErrorChecker = _CreateMultiErrorChecker(
                logger,
                root,
                targetCoqFileRelativePath,
                projectChecker,
                extraErrorCount: 0);
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                new RecordingLlmSession(new LlmChat("draft")),
                multiErrorChecker,
                "Goal.");

            var result = await proofRunOrchestrator.RunAsync(CancellationToken.None);

            Assert.False(result.Success);
            Assert.Null(result.LastError);
            Assert.Equal("draft", result.LastAssistantText);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    [Fact]
    public async Task RunAsync_WhenCheckSucceeds_RunCheckToolOnSameMultiErrorCheckerAlsoReportsSuccess()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var successCheck = new CoqCheck(CoqCheckType.Success, null, "", _CheckTimeoutSeconds);
            var projectChecker = new QueueCoqProjectChecker(new[] { successCheck, successCheck });
            var multiErrorChecker = _CreateMultiErrorChecker(logger, root, targetCoqFileRelativePath, projectChecker);
            var runCheckTool = _CreateRunCheckTool(logger);
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                new RecordingLlmSession(new LlmChat("draft")),
                multiErrorChecker,
                "Goal.");

            var agentResult = await proofRunOrchestrator.RunAsync(CancellationToken.None);
            var toolOutput = await _RunRunCheckToolAsync(root, logger, multiErrorChecker, runCheckTool);

            Assert.True(agentResult.Success);
            Assert.Equal(_ExpectedEarlySuccessAssistantText, agentResult.LastAssistantText);
            Assert.Contains("proof check succeeded", toolOutput, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    [Fact]
    public async Task RunAsync_WhenCheckFails_RunCheckToolOnSameMultiErrorCheckerReportsMatchingFailure()
    {
        var root = _NewTempProjectDir();
        try
        {
            var logger = TestInjectedLogger.CreateFatalOnly();
            var targetCoqFileRelativePath = PathTests.Rel("T.v", root);
            var coqError = PathTests.Error("T.v", 3, 1, "cannot unify", root);
            var failedCheck = new CoqCheck(CoqCheckType.Failed, coqError, "raw", _CheckTimeoutSeconds);
            var projectChecker = new QueueCoqProjectChecker(new[] { failedCheck, failedCheck, failedCheck });
            var multiErrorChecker = _CreateMultiErrorChecker(
                logger,
                root,
                targetCoqFileRelativePath,
                projectChecker,
                extraErrorCount: 0);
            var runCheckTool = _CreateRunCheckTool(logger);
            var proofRunOrchestrator = _CreateProofRunOrchestrator(
                logger,
                root,
                new RecordingLlmSession(new LlmChat("draft")),
                multiErrorChecker,
                "Goal.");

            var agentResult = await proofRunOrchestrator.RunAsync(CancellationToken.None);
            var toolOutput = await _RunRunCheckToolAsync(root, logger, multiErrorChecker, runCheckTool);

            Assert.False(agentResult.Success);
            Assert.Same(coqError, agentResult.LastError);
            Assert.Contains("proof check failed", toolOutput, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("cannot unify", toolOutput, StringComparison.Ordinal);
            Assert.Contains(coqError.ToString(), toolOutput, StringComparison.Ordinal);
        }
        finally
        {
            _TryDeleteTempDir(root);
        }
    }

    private static RunMultiErrorCheckTool _CreateRunCheckTool(ILogger logger)
    {
        return new RunMultiErrorCheckTool(PromptTestFixtures.CreateToolDeclarationLoader(logger));
    }

    private static async Task<string> _RunRunCheckToolAsync(
        string projectRoot,
        ILogger logger,
        CoqMultiErrorChecker multiErrorChecker,
        RunMultiErrorCheckTool runCheckTool)
    {
        var toolContext = ToolExecutionContextTestFixtures.CreateWithRunCheck(
            projectRoot,
            multiErrorChecker,
            PromptTestFixtures.CreateRunCheckToolResultFormatter(logger));
        return await runCheckTool.RunAsync(
            toolContext,
            JsonDocument.Parse("{}").RootElement,
            CancellationToken.None);
    }

    private static CoqProofRunOrchestrator _CreateProofRunOrchestrator(
        ILogger logger,
        string projectRoot,
        ILlmSession proofSession,
        CoqMultiErrorChecker multiErrorChecker,
        string initialUserMessage,
        Dictionary<string, IReadOnlyList<CoqSentence>>? sentencesByPath = null)
    {
        var resolvedSentences = sentencesByPath ?? new Dictionary<string, IReadOnlyList<CoqSentence>>();
        _EnsureCoqProjectFilesExist(projectRoot, resolvedSentences);
        var fileSystem = new ProjectFileSystem(projectRoot);
        var definitionDatabase = new DefinitionDatabase(logger);
        var lemmaDatabase = new LemmaDatabase(logger);
        var sentenceSplitter = new PathKeyedCoqSentenceSplitter(resolvedSentences);
        var coqKnowledgeCollector = new CoqKnowledgeCollector(definitionDatabase, logger);
        return new CoqProofRunOrchestrator(
            initialUserMessage,
            coqKnowledgeCollector,
            definitionDatabase,
            lemmaDatabase,
            fileSystem,
            sentenceSplitter,
            proofSession,
            multiErrorChecker,
            logger,
            PromptTestFixtures.CreatePromptTextSource(logger),
            new LlmChatOptions(true, "high"));
    }

    private static void _EnsureCoqProjectFilesExist(
        string projectRoot,
        Dictionary<string, IReadOnlyList<CoqSentence>> sentencesByPath)
    {
        foreach (var relativePath in sentencesByPath.Keys)
        {
            var fullPath = Path.Combine(projectRoot, relativePath);
            var parent = Path.GetDirectoryName(fullPath);
            if (!string.IsNullOrWhiteSpace(parent))
            {
                Directory.CreateDirectory(parent);
            }

            if (!File.Exists(fullPath))
            {
                File.WriteAllText(fullPath, "");
            }
        }
    }

    private static string _NewTempProjectDir()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentProofRun_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, "T.v"), "");
        return root;
    }

    private static void _TryDeleteTempDir(string root)
    {
        try
        {
            Directory.Delete(root, recursive: true);
        }
        catch
        {
            // Best-effort cleanup for temp test directories.
        }
    }

    private static CoqMultiErrorChecker _CreateMultiErrorChecker(
        ILogger logger,
        string tempDir,
        RelativePath targetCoqFileRelativePath,
        ICoqChecker projectChecker,
        string environmentText = "env-fixed",
        int extraErrorCount = 2)
    {
        var fileSystem = new ProjectFileSystem(tempDir);
        var sentenceSplitter = new FixedCoqSentenceSplitter(Array.Empty<CoqSentence>());
        var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        var bulletAnalyzer = new CoqBulletAnalyzer(logger, sentenceSplitter, sentenceAnalyzer);
        var planner = new CoqProofBulletIterationPlanner(logger, bulletAnalyzer, sentenceSplitter);
        var environment = new FixedCoqEnvironmentTextSource(environmentText);
        return new CoqMultiErrorChecker(
            logger,
            projectChecker,
            environment,
            targetCoqFileRelativePath,
            fileSystem,
            planner,
            _CheckTimeoutSeconds,
            "make",
            extraErrorCount);
    }

    private static CoqSentence _Sentence(
        CoqSentenceVernacType vernacType,
        string name,
        int startLineOneBased,
        int endLineOneBased,
        string text)
    {
        return new CoqSentence
        {
            VernacType = vernacType,
            Name = name,
            StartLineOneBased = startLineOneBased,
            EndLineOneBased = endLineOneBased,
            Text = text,
        };
    }
}
