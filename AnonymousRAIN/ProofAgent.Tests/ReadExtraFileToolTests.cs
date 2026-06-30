using System.Text.Json;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class ReadExtraFileToolTests
{
    [Fact]
    public async Task RunAsync_Range_ReturnsExactLinesWithAbsolutePath()
    {
        var projectRoot = Path.Combine(Path.GetTempPath(), "ProofAgentReadExtProj_" + Guid.NewGuid().ToString("N"));
        var externalRoot = Path.Combine(Path.GetTempPath(), "ProofAgentReadExtLib_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(projectRoot);
        Directory.CreateDirectory(externalRoot);
        var externalFile = Path.Combine(externalRoot, "X.v");
        File.WriteAllLines(externalFile, new[] { "l1", "l2", "l3", "l4" });
        try
        {
            var projectFs = new ProjectFileSystem(projectRoot);
            IReadOnlyFileSystem externalFs = new ReadOnlyFileSystem(externalRoot);
            var ctx = ToolExecutionContextTestFixtures.CreateWithExtraReadableRoots(
                projectFs,
                new IReadOnlyFileSystem[] { externalFs },
                searchHitContextLines: 2);
            var tool = new ReadExtraFileTool(
                PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse(
                $$"""{"path":{{JsonSerializer.Serialize(Path.GetFullPath(externalFile))}},"startLine":2,"endLine":3}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Equal(
                string.Join(Environment.NewLine, new[] { "...", "2: l2", "3: l3", "..." }),
                result);
        }
        finally
        {
            try
            {
                Directory.Delete(projectRoot, recursive: true);
                Directory.Delete(externalRoot, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public async Task RunAsync_PathOutsideExtraReadableRoots_ReturnsError()
    {
        var projectRoot = Path.Combine(Path.GetTempPath(), "ProofAgentReadExtOut_" + Guid.NewGuid().ToString("N"));
        var externalRoot = Path.Combine(Path.GetTempPath(), "ProofAgentReadExtLibOut_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(projectRoot);
        Directory.CreateDirectory(externalRoot);
        var projectFile = Path.Combine(projectRoot, "OnlyInProject.v");
        File.WriteAllText(projectFile, "content\n");
        try
        {
            var projectFs = new ProjectFileSystem(projectRoot);
            IReadOnlyFileSystem externalFs = new ReadOnlyFileSystem(externalRoot);
            var ctx = ToolExecutionContextTestFixtures.CreateWithExtraReadableRoots(
                projectFs,
                new IReadOnlyFileSystem[] { externalFs },
                searchHitContextLines: 2);
            var tool = new ReadExtraFileTool(
                PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse(
                $$"""{"path":{{JsonSerializer.Serialize(Path.GetFullPath(projectFile))}},"startLine":1,"endLine":1}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Equal(
                "path must resolve under a directory listed in extraReadableRootPaths.",
                result);
        }
        finally
        {
            try
            {
                Directory.Delete(projectRoot, recursive: true);
                Directory.Delete(externalRoot, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public async Task RunAsync_RelativePath_ReturnsError()
    {
        var projectRoot = Path.Combine(Path.GetTempPath(), "ProofAgentReadExtRel_" + Guid.NewGuid().ToString("N"));
        var externalRoot = Path.Combine(Path.GetTempPath(), "ProofAgentReadExtLibRel_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(projectRoot);
        Directory.CreateDirectory(externalRoot);
        try
        {
            var projectFs = new ProjectFileSystem(projectRoot);
            IReadOnlyFileSystem externalFs = new ReadOnlyFileSystem(externalRoot);
            var ctx = ToolExecutionContextTestFixtures.CreateWithExtraReadableRoots(
                projectFs,
                new IReadOnlyFileSystem[] { externalFs },
                searchHitContextLines: 2);
            var tool = new ReadExtraFileTool(
                PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"X.v","startLine":1,"endLine":1}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Equal(
                "path must be an absolute file path under a directory listed in extraReadableRootPaths.",
                result);
        }
        finally
        {
            try
            {
                Directory.Delete(projectRoot, recursive: true);
                Directory.Delete(externalRoot, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }
}
