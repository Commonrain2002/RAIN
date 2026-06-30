using ProofAgent.Llm;
using ProofAgent.Session;
using ProofAgent.Tests.Fakes;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class LlmSessionTests
{
    private const int DefaultMaxToolRounds = 5000;

    private static readonly LlmChatOptions _DefaultChatOptions = new(false, "low");

    private static ReplaceBlockInFileTool _CreateReplaceTool(ILogger logger)
    {
        return new ReplaceBlockInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(logger));
    }

    [Fact]
    public async Task ChatAsync_NoToolCalls_Completes()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse("hello", Array.Empty<ToolCall>()));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var toolExecution = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var session = new LlmSession(
            provider,
            registry,
            toolExecution,
            new PassThroughContextCompressor(),
            "",
            logger,
            DefaultMaxToolRounds);

        var result = await session.ChatAsync("hi", _DefaultChatOptions, CancellationToken.None);

        Assert.Equal("hello", result.LastAssistantText);
        Assert.Equal(LlmUsage.Zero, result.TotalUsage);
        Assert.Equal(LlmParticipantRole.User, session.History[0].Role);
        Assert.Equal(LlmParticipantRole.Assistant, session.History[1].Role);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_InvalidToolArgumentsJson_RecordsToolErrorAndContinues()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse(
            "",
            new[] { new ToolCall("c1", "replace", """{"path":"f.txt","oldText"=broken""") }));
        provider.Enqueue(new LlmResponse("retry", Array.Empty<ToolCall>()));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a" });
        var toolExecution = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var session = new LlmSession(
            provider,
            registry,
            toolExecution,
            new PassThroughContextCompressor(),
            "",
            logger,
            DefaultMaxToolRounds);

        var result = await session.ChatAsync("edit", _DefaultChatOptions, CancellationToken.None);

        Assert.Equal("retry", result.LastAssistantText);
        var toolMessages = session.History.Where(static m => m.Role == LlmParticipantRole.Tool).ToList();
        Assert.Single(toolMessages);
        Assert.Equal("c1", toolMessages[0].ToolCallID);
        Assert.Contains("Invalid tool arguments JSON", toolMessages[0].Content, StringComparison.Ordinal);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_MultipleToolCalls_RunInOrderUsingCurrentFileLines()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse(
            "",
            new[]
            {
                new ToolCall("c1", "replace", """{"path":"f.txt","oldText":"a","newText":"z\na"}"""),
                new ToolCall("c2", "replace", """{"path":"f.txt","oldText":"b\nc","newText":"b"}""")
            }));
        provider.Enqueue(new LlmResponse("done", Array.Empty<ToolCall>()));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a", "b", "c" });
        var toolExecution = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var session = new LlmSession(
            provider,
            registry,
            toolExecution,
            new PassThroughContextCompressor(),
            "",
            logger,
            DefaultMaxToolRounds);

        var result = await session.ChatAsync("edit", _DefaultChatOptions, CancellationToken.None);

        Assert.Equal("done", result.LastAssistantText);
        Assert.Equal(LlmUsage.Zero, result.TotalUsage);
        Assert.Equal(new[] { "z", "a", "b" }, File.ReadAllLines(Path.Combine(root, "f.txt")));

        var toolMessages = session.History.Where(static m => m.Role == LlmParticipantRole.Tool).ToList();
        Assert.Equal(2, toolMessages.Count);
        Assert.Equal("c1", toolMessages[0].ToolCallID);
        Assert.Equal("c2", toolMessages[1].ToolCallID);
        Assert.Equal("ok", toolMessages[0].Content);
        Assert.Equal("ok", toolMessages[1].Content);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_SumsUsageAcrossToolRounds()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse(
            "",
            new[] { new ToolCall("c1", "replace", """{"path":"f.txt","oldText":"a","newText":"z"}""") },
            "",
            new LlmUsage(10, 2, 12)));
        provider.Enqueue(new LlmResponse("done", Array.Empty<ToolCall>(), null, new LlmUsage(5, 3, 8)));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a" });
        var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var session = new LlmSession(
            provider,
            registry,
            ctx,
            new PassThroughContextCompressor(),
            "",
            logger,
            DefaultMaxToolRounds);

        var result = await session.ChatAsync("edit", _DefaultChatOptions, CancellationToken.None);

        Assert.Equal("done", result.LastAssistantText);
        Assert.Equal(new LlmUsage(15, 5, 20), result.TotalUsage);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_OnEachHttpResponse_ReportsUsageAndMatchesGlobalSum()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse("done", Array.Empty<ToolCall>(), null, new LlmUsage(4, 1, 5)));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var reports = new List<LlmSessionUsageReport>();
        var runTotal = LlmUsage.Zero;
        Action<LlmSessionUsageReport> onEach = report =>
        {
            reports.Add(report);
            runTotal = runTotal.Add(report.ResponseUsage);
        };
        var session = new LlmSession(
            provider,
            registry,
            ctx,
            new PassThroughContextCompressor(),
            "",
            logger,
            DefaultMaxToolRounds,
            onEach);

        var result = await session.ChatAsync("hi", _DefaultChatOptions, CancellationToken.None);

        Assert.Single(reports);
        Assert.Equal(new LlmUsage(4, 1, 5), reports[0].ResponseUsage);
        Assert.Equal(reports[0].SessionCumulativeUsage, reports[0].ResponseUsage);
        Assert.Equal(runTotal, result.TotalUsage);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_OnlyToolCallsUntilMaxToolRounds_ReturnsExceededMaxToolRounds()
    {
        const int maxToolRounds = 16;
        var provider = new QueueLlmProvider();
        for (var i = 0; i < maxToolRounds; i++)
        {
            provider.Enqueue(new LlmResponse(
                "",
                new[] { new ToolCall("t" + i, "replace", """{"path":"f.txt","oldText":"p","newText":"x"}""") }));
        }

        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "p" });
        var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var session = new LlmSession(
            provider,
            registry,
            ctx,
            new PassThroughContextCompressor(),
            "",
            logger,
            maxToolRounds);

        var result = await session.ChatAsync("go", _DefaultChatOptions, CancellationToken.None);

        Assert.True(result.ExceededMaxToolRounds);
        Assert.Equal(string.Empty, result.LastAssistantText);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_NoToolCalls_CompressInvokedOncePerModelRound()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse("hi", Array.Empty<ToolCall>()));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var counting = new CountingContextCompressor(new PassThroughContextCompressor());
        var session = new LlmSession(
            provider,
            registry,
            ctx,
            counting,
            "",
            logger,
            DefaultMaxToolRounds);

        await session.ChatAsync("u", _DefaultChatOptions, CancellationToken.None);

        Assert.Equal(1, counting.CompressCallCount);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public async Task ChatAsync_ToolThenText_CompressInvokedTwice()
    {
        var provider = new QueueLlmProvider();
        provider.Enqueue(new LlmResponse(
            "",
            new[] { new ToolCall("c1", "replace", """{"path":"f.txt","oldText":"a","newText":"z"}""") }));
        provider.Enqueue(new LlmResponse("done", Array.Empty<ToolCall>()));
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a" });
        var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var registry = new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) });
        var counting = new CountingContextCompressor(new PassThroughContextCompressor());
        var session = new LlmSession(
            provider,
            registry,
            ctx,
            counting,
            "",
            logger,
            DefaultMaxToolRounds);

        await session.ChatAsync("edit", _DefaultChatOptions, CancellationToken.None);

        Assert.Equal(2, counting.CompressCallCount);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public void Constructor_WithSystemMessage_PrependsSystemToHistory()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentLlmSession_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var provider = new QueueLlmProvider();
        var session = new LlmSession(
            provider,
            new ToolRegistry(new ITool[] { _CreateReplaceTool(logger) }),
            ToolExecutionContextTestFixtures.CreateFileOnly(root, 2),
            new PassThroughContextCompressor(),
            "system-prompt",
            logger,
            DefaultMaxToolRounds);

        Assert.Equal(LlmParticipantRole.System, session.History[0].Role);
        Assert.Equal("system-prompt", session.History[0].Content);
        Directory.Delete(root, recursive: true);
    }
}
