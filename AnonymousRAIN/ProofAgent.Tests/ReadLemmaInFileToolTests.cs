using System.Text.Json;
using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class ReadLemmaInFileToolTests
{
    [Fact]
    public async Task ReadLemmaInFileTool_WhenFileHasNoIndexedLemmas_ReturnsNoLemmasMessage()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentReadLemmaEmpty_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, "Empty.v"), "");
        try
        {
            var lemmaDatabase = ToolExecutionContextTestFixtures.CreateEmptyLemmaDatabase();
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(new ProjectFileSystem(root), 0, lemmaDatabase);
            var tool = new ReadLemmaInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"Empty.v"}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Equal("No lemmas/theorems indexed in this file.", result);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReadLemmaInFileTool_ReturnsLemmasInFileOrder()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentReadLemmaHit_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, "Lib.v"), "");
        try
        {
            var lemmaDatabase = ToolExecutionContextTestFixtures.CreateEmptyLemmaDatabase();
            var path = new RelativePath("Lib.v", new AbsolutePath(root));
            lemmaDatabase.TryAddLemma(
                path,
                new CoqSentence
                {
                    VernacType = CoqSentenceVernacType.Theorem,
                    Name = "plus_comm",
                    Text = "Lemma plus_comm : forall n m, n + m = m + n.",
                });

            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(new ProjectFileSystem(root), 0, lemmaDatabase);
            var tool = new ReadLemmaInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"Lib.v"}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("Lib.v", result, StringComparison.Ordinal);
            Assert.Contains("Lemma plus_comm : forall n m, n + m = m + n.", result, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReadLemmaInFileTool_ManyLemmas_TruncatesOutputByCharLimit()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentReadLemmaCharLim_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, "Huge.v"), "");
        try
        {
            var lemmaDatabase = ToolExecutionContextTestFixtures.CreateEmptyLemmaDatabase();
            var path = new RelativePath("Huge.v", new AbsolutePath(root));
            for (var i = 0; i < 800; i++)
            {
                lemmaDatabase.TryAddLemma(
                    path,
                    new CoqSentence
                    {
                        VernacType = CoqSentenceVernacType.Theorem,
                        Name = "l" + i,
                        Text = "Lemma needle padding statement content line " + i + ".",
                    });
            }

            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(new ProjectFileSystem(root), 0, lemmaDatabase);
            var tool = new ReadLemmaInFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            using var args = JsonDocument.Parse("""{"path":"Huge.v","maxMatches":800}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("[Output truncated at 10000 characters;", result, StringComparison.Ordinal);
            Assert.True(result.Length > 10000);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
