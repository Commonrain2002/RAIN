using ProofAgent.Coq;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class CoqBulletAnalyzerTests
{
    [Fact]
    public async Task GetBulletStack_BeforeFailnowBullet_HasDashOnTop()
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

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var stackTry = await analyzer.GetBulletStackAsync(
                relativeVPath,
                lineOneBased: 4,
                columnZeroBased: 0,
                CancellationToken.None);

            Assert.True(stackTry.Succeeded, stackTry.FailureReason);
            Assert.Equal("-", stackTry.BulletStack!.Cells[^1].TrimmedToken);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task GetBulletStack_RepeatedDashAtSameLevel_CollapsesToOneDashCell()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "split.",
            "-",
            "idtac.",
            "-",
            "idtac.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
        };

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var stackTry = await analyzer.GetBulletStackAsync(
                relativeVPath,
                lineOneBased: 7,
                columnZeroBased: 0,
                CancellationToken.None);

            Assert.True(stackTry.Succeeded, stackTry.FailureReason);
            var dashCells = stackTry.BulletStack!.Cells.Where(static c => c.TrimmedToken == "-").ToList();
            Assert.Single(dashCells);
            Assert.Equal("-", stackTry.BulletStack!.Cells[^1].TrimmedToken);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task GetBulletEnd_AtFailnow_EndsOnFailnowLine()
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

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var endHeld = await analyzer.GetBulletEndAsync(relativeVPath, lineOneBased: 4, columnZeroBased: 0, CancellationToken.None);

            Assert.True(endHeld.Succeeded, endHeld.FailureReason);
            Assert.Equal(4, endHeld.EndLineOneBased);
            Assert.Equal(lines[3].Length, endHeld.EndColumnZeroBased);
            Assert.Equal(3, endHeld.LastSentenceIndex);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task GetBulletEnd_NestedStarSubgoal_StopsBeforeSiblingDashNotSecondCaseSpine()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "+",
            "idtac.",
            "+",
            "idtac.",
            "+",
            "idtac.",
            "*",
            "idtac.",
            "*",
            "idtac.",
            "admit.",
            "*",
            "idtac.",
            "fail.",
            "-",
            "idtac.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
        };

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var endHeld = await analyzer.GetBulletEndAsync(relativeVPath, lineOneBased: 17, columnZeroBased: 0, CancellationToken.None);

            Assert.True(endHeld.Succeeded, endHeld.FailureReason);
            Assert.Equal(17, endHeld.EndLineOneBased);
            Assert.Equal(lines[16].Length, endHeld.EndColumnZeroBased);
            Assert.Equal(16, endHeld.LastSentenceIndex);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task GetBulletEnd_FocusSubgoalBrace_DoesNotStopAtAssertOpenBrace()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "assert (H : True).",
            "{",
            "2: {",
            "idtac.",
            "}",
            "}",
            "fail.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(curly)",
            "VtProofStep(curly)",
            "VtProofStep",
        };

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var endHeld = await analyzer.GetBulletEndAsync(relativeVPath, lineOneBased: 10, columnZeroBased: 0, CancellationToken.None);

            Assert.True(endHeld.Succeeded, endHeld.FailureReason);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task GetBulletStack_ClosingBraceBeforeAnchor_FailsWhenWouldPopRootBrace()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "}",
            "fail.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(curly)",
            "VtProofStep",
        };

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var stackTry = await analyzer.GetBulletStackAsync(
                relativeVPath,
                lineOneBased: 4,
                columnZeroBased: 0,
                CancellationToken.None);

            Assert.False(stackTry.Succeeded);
            Assert.Null(stackTry.BulletStack);
            Assert.Contains("stack[0]", stackTry.FailureReason, StringComparison.Ordinal);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task GetBulletEnd_ClosingBraceBeforeAnchor_FailsWhenWouldPopRootBrace()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "}",
            "fail.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(curly)",
            "VtProofStep",
        };

        var (analyzer, relativeVPath, tempDir) = await _CreateAnalyzerWithTempFileAsync(lines, classByIndex);
        try
        {
            var endHeld = await analyzer.GetBulletEndAsync(relativeVPath, lineOneBased: 4, columnZeroBased: 0, CancellationToken.None);

            Assert.False(endHeld.Succeeded);
            Assert.Contains("stack[0]", endHeld.FailureReason, StringComparison.Ordinal);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    private static async Task<(CoqBulletAnalyzer Analyzer, RelativePath RelativeVPath, string TempDir)> _CreateAnalyzerWithTempFileAsync(
        string[] lines,
        string[] classificationByAscendingIndexExclusive)
    {
        var sentencesRecordList = CoqLineAlignedSentenceTestHelper.SentencesLineAlignedOnePerPhysicalLine(
            lines,
            classificationByAscendingIndexExclusive);
        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentBullet_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        await File.WriteAllLinesAsync(Path.Combine(tempDir, "A.v"), lines).ConfigureAwait(false);
        ILogger logger = TestInjectedLogger.CreateFatalOnly();
        var sentenceSplitter = new FixedCoqSentenceSplitter(sentencesRecordList);
        var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        var analyzer = new CoqBulletAnalyzer(logger, sentenceSplitter, sentenceAnalyzer);
        return (analyzer, new RelativePath("A.v", new AbsolutePath(tempDir)), tempDir);
    }

    private static void _TryDeleteTempDirForPath(string tempDir)
    {
        try
        {
            var dir = tempDir;
            if (dir != null && Directory.Exists(dir))
            {
                Directory.Delete(dir, recursive: true);
            }
        }
        catch
        {
            // best-effort cleanup
        }
    }
}
