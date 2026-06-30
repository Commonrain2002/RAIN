using ProofAgent.Coq;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class CoqSentenceAnalyzerTests
{
    [Fact]
    public async Task GetSentenceAtPosition_StartOfFailnowLine_ReturnsFailnowSentence()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "failnow.",
            "-",
            "idtac.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
        };

        CoqLineAlignedSentenceTestHelper.SentencesLineAlignedOnePerPhysicalLine(lines, classByIndex);

        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentSentenceAtPosition_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            var (sentenceAnalyzer, fileSystem) = _CreateSentenceAnalyzer(tempDir);
            File.WriteAllLines(Path.Combine(tempDir, "A.v"), lines);
            var atHeld = await sentenceAnalyzer
                .GetSentenceAtPositionAsync(fileSystem.Rel("A.v"), lineOneBased: 4, columnZeroBased: 0, CancellationToken.None);

            Assert.NotNull(atHeld);
            Assert.Equal("failnow.", atHeld!.Text);
            Assert.Equal(3, atHeld.Index);
        }
        finally
        {
            try
            {
                Directory.Delete(tempDir, true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public async Task GetSentenceBefore_StartOfFailnowLine_ReturnsPriorBulletSentence()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "failnow.",
            "-",
            "idtac.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
        };

        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentSentenceAnalyzer_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            var (sentenceAnalyzer, fileSystem) = _CreateSentenceAnalyzer(tempDir);
            File.WriteAllLines(Path.Combine(tempDir, "A.v"), lines);
            var asyncBefore = await sentenceAnalyzer
                .GetSentenceBeforeAsync(fileSystem.Rel("A.v"), lineOneBased: 4, columnZeroBased: 0, CancellationToken.None);

            Assert.NotNull(asyncBefore);
            Assert.Equal("-", asyncBefore!.Text);
            Assert.Equal(2, asyncBefore.Index);
        }
        finally
        {
            try
            {
                Directory.Delete(tempDir, true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public async Task GetSentenceBefore_AtEndOfPhysicalLine_ReturnsSentenceWhenCursorStillInsideSpan()
    {
        var lines = new[] { "Lemma u : True.", "Proof.", "idtac." };
        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep",
        };

        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentSentenceAnalyzerMid_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        try
        {
            var (sentenceAnalyzer, fileSystem) = _CreateSentenceAnalyzer(tempDir);
            File.WriteAllLines(Path.Combine(tempDir, "B.v"), lines);
            var idtacLineIndex = 2;
            var columnInsideIdtacLine = lines[idtacLineIndex].Length - 1;
            var beforeHeld = await sentenceAnalyzer
                .GetSentenceBeforeAsync(
                    fileSystem.Rel("B.v"),
                    lineOneBased: idtacLineIndex + 1,
                    columnZeroBased: columnInsideIdtacLine,
                    CancellationToken.None);

            Assert.NotNull(beforeHeld);
            Assert.Equal("Proof.", beforeHeld!.Text);
        }
        finally
        {
            try
            {
                Directory.Delete(tempDir, true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    private static (CoqSentenceAnalyzer Analyzer, ProjectFileSystem FileSystem) _CreateSentenceAnalyzer(string projectRoot)
    {
        ILogger logger = TestInjectedLogger.CreateFatalOnly();
        var fileSystem = new ProjectFileSystem(projectRoot);
        var sentenceSplitter = new LineCoqSentenceSplitterTests(fileSystem);
        var analyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        return (analyzer, fileSystem);
    }
}
