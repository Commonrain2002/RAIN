using System.Text.Json;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class ReplaceToolTests
{
    private static string _OldTextNotFoundMessage =>
        ReflectionTestAccess.GetStaticFieldNonPublic<string>(typeof(ToolExecutionContext), "_OldTextNotFound")!;

    private static string _AmbiguousMatchMessage =>
        ReflectionTestAccess.GetStaticFieldNonPublic<string>(typeof(ToolExecutionContext), "_AmbiguousMatch")!;

    private static TestTempRoot CreateTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentReplaceTool_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        return new TestTempRoot(root, new ProjectFileSystem(root));
    }

    [Fact]
    public async Task ReplaceTool_UniqueMatchInFile_ReplacesOldText_WritesToDisk()
    {
        var temp = CreateTempRoot();
        var root = temp.RootPath;
        var fs = temp.FileSystem;
        try
        {
            var path = Path.Combine(root, "f.txt");
            File.WriteAllLines(path, new[] { "a", "b", "c" });
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            var tool = new ReplaceBlockInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"f.txt","oldText":"b\nc","newText":"y"}""");
            Assert.Equal("ok", await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None));
            Assert.Equal(new[] { "a", "y" }, File.ReadAllLines(path));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReplaceTool_OldTextNotFoundInFile_ReturnsMessage_DoesNotWrite()
    {
        var temp = CreateTempRoot();
        var root = temp.RootPath;
        var fs = temp.FileSystem;
        try
        {
            var path = Path.Combine(root, "f.txt");
            File.WriteAllLines(path, new[] { "a", "b", "c" });
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            var tool = new ReplaceBlockInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"f.txt","oldText":"z","newText":"y"}""");
            Assert.Equal(_OldTextNotFoundMessage, await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None));
            Assert.Equal(new[] { "a", "b", "c" }, File.ReadAllLines(path));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReplaceTool_AmbiguousMatchInFile_ReturnsMessage()
    {
        var temp = CreateTempRoot();
        var root = temp.RootPath;
        var fs = temp.FileSystem;
        try
        {
            var path = Path.Combine(root, "f.txt");
            File.WriteAllText(path, "xxx");
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            var tool = new ReplaceBlockInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"f.txt","oldText":"xx","newText":"y"}""");
            Assert.Equal(_AmbiguousMatchMessage, await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None));
            Assert.Equal("xxx", File.ReadAllText(path));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
