using System.Text.Json;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class ToolRegistryTests
{
    [Fact]
    public void Constructor_DuplicateToolNames_ThrowsArgumentException()
    {
        var loader = PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly());
        var ex = Assert.Throws<ArgumentException>(() =>
            new ToolRegistry(new ITool[]
            {
                new ReplaceBlockInFileTool(loader),
                new ReplaceBlockInFileTool(loader)
            }));
        Assert.Contains("Duplicate", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Run_UnknownTool_ReturnsMessage()
    {
        var registry = new ToolRegistry(new[] { new ReplaceBlockInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly())) });
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentToolRegistry_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
        using var doc = JsonDocument.Parse(
            """{"path":"a.txt","oldText":"x","newText":"y"}""");
        var result = await registry.RunAsync(ctx, "no_such_tool", doc.RootElement.Clone(), CancellationToken.None);
        Assert.Equal("Unknown tool: no_such_tool", result);
        Directory.Delete(root, recursive: true);
    }

    [Fact]
    public void GetDeclarations_CountMatchesRegisteredTools_AndNameMatchesDeclaration()
    {
        var tools = new ITool[] { new ReplaceBlockInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly())) };
        var registry = new ToolRegistry(tools);
        var decls = registry.GetDeclarations();
        Assert.Single(decls);
        foreach (var tool in tools)
        {
            var match = decls.Single(d => d.GetProperty("name").GetString() == tool.Name);
            Assert.NotEqual(default, match);
        }
    }
}
