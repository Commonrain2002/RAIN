using System.Text.Json;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class SearchExtraByRegexToolTests
{
    [Fact]
    public async Task RunAsync_FindsMatchInExtraReadableRoot_ReturnsAbsolutePathLine()
    {
        var projectRoot = Path.Combine(Path.GetTempPath(), "ProofAgentExtSearchProj_" + Guid.NewGuid().ToString("N"));
        var externalRoot = Path.Combine(Path.GetTempPath(), "ProofAgentExtSearchLib_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(projectRoot);
        Directory.CreateDirectory(externalRoot);
        var externalFile = Path.Combine(externalRoot, "LemmaLib.v");
        File.WriteAllText(externalFile, "Lemma external_lemma.\n");
        try
        {
            var projectFs = new ProjectFileSystem(projectRoot);
            IReadOnlyFileSystem externalFs = new ReadOnlyFileSystem(externalRoot);
            var ctx = ToolExecutionContextTestFixtures.CreateWithExtraReadableRoots(
                projectFs,
                new IReadOnlyFileSystem[] { externalFs },
                searchHitContextLines: 0);
            var tool = new SearchExtraByRegexTool(
                PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var args = JsonSerializer.SerializeToElement(new { pattern = "external_lemma" });
            var result = await tool.RunAsync(ctx, args, CancellationToken.None);
            var expectedPathLine = $"{Path.GetFullPath(externalFile)}:1";
            Assert.Contains(expectedPathLine, result, StringComparison.Ordinal);
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
    public async Task RunAsync_OffsetAcrossTwoRoots_PaginatesGlobally()
    {
        var projectRoot = Path.Combine(Path.GetTempPath(), "ProofAgentExtOffProj_" + Guid.NewGuid().ToString("N"));
        var externalRootA = Path.Combine(Path.GetTempPath(), "ProofAgentExtOffA_" + Guid.NewGuid().ToString("N"));
        var externalRootB = Path.Combine(Path.GetTempPath(), "ProofAgentExtOffB_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(projectRoot);
        Directory.CreateDirectory(externalRootA);
        Directory.CreateDirectory(externalRootB);
        File.WriteAllText(Path.Combine(externalRootA, "a.v"), "hit marker_a\n");
        File.WriteAllText(Path.Combine(externalRootB, "b.v"), "hit marker_b\n");
        try
        {
            var projectFs = new ProjectFileSystem(projectRoot);
            IReadOnlyFileSystem externalFsA = new ReadOnlyFileSystem(externalRootA);
            IReadOnlyFileSystem externalFsB = new ReadOnlyFileSystem(externalRootB);
            var ctx = ToolExecutionContextTestFixtures.CreateWithExtraReadableRoots(
                projectFs,
                new IReadOnlyFileSystem[] { externalFsA, externalFsB },
                searchHitContextLines: 0);
            var tool = new SearchExtraByRegexTool(
                PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var args = JsonSerializer.SerializeToElement(new { pattern = "marker_", offset = 1, maxMatches = 1 });
            var result = await tool.RunAsync(ctx, args, CancellationToken.None);
            var expectedPathLine = $"{Path.GetFullPath(Path.Combine(externalRootB, "b.v"))}:1";
            Assert.Contains(expectedPathLine, result, StringComparison.Ordinal);
            Assert.DoesNotContain(Path.GetFullPath(Path.Combine(externalRootA, "a.v")), result, StringComparison.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(projectRoot, recursive: true);
                Directory.Delete(externalRootA, recursive: true);
                Directory.Delete(externalRootB, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }
}
