using ProofAgent.Coq;
using ProofAgent.Llm;
using ProofAgent.Session;
using ProofAgent.Tools;
using ProofAgent.Tests.Fakes;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class DifferentBulletCompressorTests
{
    [Fact]
    public void Compress_NoReplace_ReturnsOriginalReference()
    {
        var messages = new List<LlmMessage>
        {
            LlmMessage.CreateAssistant("", new[] { new ToolCall("c1", "run_check", "{}") }),
            LlmMessage.CreateTool("c1", _FailedRunCheckBody("File \"A.v\", line 4, character 0: boom"))
        };

        var compressor = _CreateCompressorWithTempFile(_SampleLines(), _SampleClassifications());
        var compressed = compressor.Compress(messages);
        Assert.Same(messages, compressed);
    }

    [Fact]
    public void Compress_LastNotRunCheck_ReturnsOriginal()
    {
        var messages = new List<LlmMessage>
        {
            LlmMessage.CreateAssistant("", new[] { new ToolCall("r1", "replace", "{}") }),
            LlmMessage.CreateTool("r1", "ok"),
            LlmMessage.CreateAssistant("done", Array.Empty<ToolCall>())
        };

        var compressor = _CreateCompressorWithTempFile(_SampleLines(), _SampleClassifications());
        var compressed = compressor.Compress(messages);
        Assert.Same(messages, compressed);
    }

    [Fact]
    public void Compress_RunCheckSucceeded_ReturnsOriginal()
    {
        var messages = _MessagesWithReplaceAndRunCheck("Result: proof check succeeded (exit code 0).");
        var compressor = _CreateCompressorWithTempFile(_SampleLines(), _SampleClassifications());
        var compressed = compressor.Compress(messages);
        Assert.Same(messages, compressed);
    }

    [Fact]
    public void Compress_FirstFailedRunCheck_InitializesSnapshotOnly()
    {
        var messages = _MessagesWithReplaceAndRunCheck(_FailedRunCheckBody(
            "File \"A.v\", line 4, character 0: boom"));
        var compressor = _CreateCompressorWithTempFile(_SampleLines(), _SampleClassifications());
        var compressed = compressor.Compress(messages);
        Assert.Same(messages, compressed);
        Assert.Equal(messages.Count, compressed.Count);
    }

    [Fact]
    public void Compress_BottomPrefixChanged_TruncatesAndRewritesReplaceTool()
    {
        var runCheckBody = _FailedRunCheckBody(
            "File \"A.v\", line 4, character 0: boom");
        var messagesEndingWithRunCheck = _MessagesWithReplaceAndRunCheck(runCheckBody);

        var compressor = _CreateCompressorWithTempFile(_SampleLines(), _SampleClassifications());
        _ = compressor.Compress(messagesEndingWithRunCheck);

        Assert.NotNull(_ReadSavedBottomPrefix(compressor));
        _WriteSavedBottomPrefix(
            compressor,
            new CoqBulletStackBottomPrefixSnapshot(new ulong[] { 99, 88 }));

        var compressed = compressor.Compress(messagesEndingWithRunCheck);
        Assert.NotSame(messagesEndingWithRunCheck, compressed);
        Assert.Equal(2, compressed.Count);
        Assert.Equal(LlmParticipantRole.Tool, compressed[^1].Role);
        Assert.Equal("rep1", compressed[^1].ToolCallID);
        Assert.StartsWith(
            ReflectionTestAccess.GetStaticFieldNonPublic<string>(
                typeof(DifferentBulletCompressor),
                "_ReplaceFrameworkAdjustmentToolResultPrefix")!,
            compressed[^1].Content,
            StringComparison.Ordinal);
        Assert.Contains(runCheckBody, compressed[^1].Content, StringComparison.Ordinal);
    }

    private static CoqBulletStackBottomPrefixSnapshot? _ReadSavedBottomPrefix(DifferentBulletCompressor compressor)
    {
        var field = typeof(DifferentBulletCompressor).GetField(
            "_SavedBottomPrefix",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        return (CoqBulletStackBottomPrefixSnapshot?)field!.GetValue(compressor);
    }

    private static void _WriteSavedBottomPrefix(
        DifferentBulletCompressor compressor,
        CoqBulletStackBottomPrefixSnapshot snapshot)
    {
        var field = typeof(DifferentBulletCompressor).GetField(
            "_SavedBottomPrefix",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        field!.SetValue(compressor, snapshot);
    }

    private static List<LlmMessage> _MessagesWithReplaceAndRunCheck(string runCheckContent)
    {
        return new List<LlmMessage>
        {
            LlmMessage.CreateAssistant("", new[] { new ToolCall("rep1", "replace", "{}") }),
            LlmMessage.CreateTool("rep1", "ok"),
            LlmMessage.CreateAssistant("", new[] { new ToolCall("rc1", "run_check", "{}") }),
            LlmMessage.CreateTool("rc1", runCheckContent)
        };
    }

    private static string _FailedRunCheckBody(string coqErrorLine)
    {
        return $"""
            Result: proof check failed.

            ## Coq Error Message
            {coqErrorLine}

            ## Error line around
            (none)

            ## Environment before error
            (none)
            """;
    }

    private static string[] _SampleLines()
    {
        return new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "failnow.",
            "-",
            "idtac.",
        };
    }

    private static string[] _SampleClassifications()
    {
        return new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
        };
    }

    private static DifferentBulletCompressor _CreateCompressorWithTempFile(
        string[] lines,
        string[] classifications)
    {
        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentDiffBullet_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        var vPath = Path.Combine(tempDir, "A.v");
        File.WriteAllLines(vPath, lines);
        var sentences = CoqLineAlignedSentenceTestHelper.SentencesLineAlignedOnePerPhysicalLine(lines, classifications);
        var splitter = new FixedCoqSentenceSplitter(sentences);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, splitter);
        var analyzer = new CoqBulletAnalyzer(logger, splitter, sentenceAnalyzer);
        var runCheckErrorAnchorParser = new RunCheckToolResultCoqErrorAnchorParser();
        var fileSystem = new ProjectFileSystem(tempDir);
        var targetPath = fileSystem.Rel("A.v");
        var proofTools = _CreateReplaceAndRunCheckTools(
            fileSystem,
            targetPath,
            splitter,
            sentenceAnalyzer,
            analyzer,
            logger);
        return new DifferentBulletCompressor(
            fileSystem,
            targetPath,
            analyzer,
            sentenceAnalyzer,
            logger,
            runCheckErrorAnchorParser,
            proofTools.ReplaceTool.Name,
            proofTools.RunCheckTool.Name);
    }

    private sealed class ReplaceAndRunCheckTools
    {
        public ReplaceAndRunCheckTools(
            ReplaceBlockInFileTool replaceTool,
            RunMultiErrorCheckTool runCheckTool)
        {
            ReplaceTool = replaceTool ?? throw new ArgumentNullException(nameof(replaceTool));
            RunCheckTool = runCheckTool ?? throw new ArgumentNullException(nameof(runCheckTool));
        }

        public ReplaceBlockInFileTool ReplaceTool { get; }

        public RunMultiErrorCheckTool RunCheckTool { get; }
    }

    private static ReplaceAndRunCheckTools _CreateReplaceAndRunCheckTools(
        ProjectFileSystem fileSystem,
        RelativePath targetPath,
        FixedCoqSentenceSplitter splitter,
        ICoqSentenceAnalyzer sentenceAnalyzer,
        CoqBulletAnalyzer bulletAnalyzer,
        ILogger logger)
    {
        var toolDeclarations = PromptTestFixtures.CreateToolDeclarationLoader(logger);
        var replaceTool = new ReplaceBlockInFileTool(toolDeclarations);
        var planner = new CoqProofBulletIterationPlanner(logger, bulletAnalyzer, splitter);
        var environment = new FixedCoqEnvironmentTextSource("env-fixed");
        var projectChecker = new QueueCoqProjectChecker(new[]
        {
            new CoqCheck(CoqCheckType.Success, null, "", 60)
        });
        var multiErrorChecker = new CoqMultiErrorChecker(
            logger,
            projectChecker,
            environment,
            targetPath,
            fileSystem,
            planner,
            60,
            "make",
            2);
        var runCheckTool = new RunMultiErrorCheckTool(toolDeclarations);
        return new ReplaceAndRunCheckTools(replaceTool, runCheckTool);
    }

}
