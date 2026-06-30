using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class CoqProofSkipFinderTests
{
    private static CoqProofSkip? Find(string[] lines)
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSkip_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        const string relativePath = "Test.v";
        try
        {
            File.WriteAllLines(Path.Combine(root, relativePath), lines);
            var fileSystem = new ProjectFileSystem(root);
            return new CoqProofSkipFinder(fileSystem).FindFirstProofSkip(fileSystem.Rel(relativePath));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void FindFirstProofSkip_FindsAdmitted()
    {
        var proofSkip = Find(new[] { "Lemma x : True.", "Proof.", "  exact I.", "Admitted." });
        Assert.NotNull(proofSkip);
        Assert.Equal(4, proofSkip!.LineOneBased);
        Assert.Equal(0, proofSkip.ColumnZeroBased);
        Assert.Equal(CoqProofSkipType.Admitted, proofSkip.Type);
    }

    [Fact]
    public void FindFirstProofSkip_SkipsExactAdmittedIdentifier()
    {
        var proofSkip = Find(new[] { "Definition exactAdmitted := 0.", "Admitted." });
        Assert.NotNull(proofSkip);
        Assert.Equal(2, proofSkip!.LineOneBased);
        Assert.Equal(CoqProofSkipType.Admitted, proofSkip.Type);
    }

    [Fact]
    public void FindFirstProofSkip_IndentedAdmitted()
    {
        var proofSkip = Find(new[] { "  Admitted." });
        Assert.NotNull(proofSkip);
        Assert.Equal(2, proofSkip!.ColumnZeroBased);
        Assert.Equal(CoqProofSkipType.Admitted, proofSkip.Type);
    }

    [Fact]
    public void FindFirstProofSkip_FindsAbort()
    {
        var proofSkip = Find(new[] { "Lemma x : True.", "Proof.", "  Abort." });
        Assert.NotNull(proofSkip);
        Assert.Equal(3, proofSkip!.LineOneBased);
        Assert.Equal(CoqProofSkipType.Abort, proofSkip.Type);
    }

    [Fact]
    public void FindFirstProofSkip_AbortBeforeAdmitted()
    {
        var proofSkip = Find(new[] { "Proof.", "Abort.", "Admitted." });
        Assert.NotNull(proofSkip);
        Assert.Equal(2, proofSkip!.LineOneBased);
        Assert.Equal(CoqProofSkipType.Abort, proofSkip.Type);
    }

    [Fact]
    public void FindFirstProofSkip_AdmittedBeforeAbort()
    {
        var proofSkip = Find(new[] { "Proof.", "Admitted.", "Abort." });
        Assert.NotNull(proofSkip);
        Assert.Equal(2, proofSkip!.LineOneBased);
        Assert.Equal(CoqProofSkipType.Admitted, proofSkip.Type);
    }

    [Fact]
    public void FindFirstProofSkip_None_ReturnsNull()
    {
        Assert.Null(Find(new[] { "Qed.", "Require Import Arith." }));
    }

    [Fact]
    public void FindFirstProofSkip_IgnoresInsideBlockComment_OnSameLine()
    {
        var proofSkip = Find(new[]
        {
            "Lemma x : True.",
            "Proof. (* Admitted. *)",
            "exact I.",
            "Admitted."
        });
        Assert.NotNull(proofSkip);
        Assert.Equal(4, proofSkip!.LineOneBased);
    }

    [Fact]
    public void FindFirstProofSkip_IgnoresWhenOnlyInComment()
    {
        Assert.Null(Find(new[] { "(* Admitted. *)", "Qed." }));
    }

    [Fact]
    public void FindFirstProofSkip_IgnoresInsideString()
    {
        var proofSkip = Find(new[] { "Definition x := \"Admitted.\".", "Admitted." });
        Assert.NotNull(proofSkip);
        Assert.Equal(2, proofSkip!.LineOneBased);
    }

    [Fact]
    public void FindFirstProofSkip_IgnoresMultilineComment()
    {
        var proofSkip = Find(new[]
        {
            "Proof. (*",
            "Admitted.",
            "*) Admitted."
        });
        Assert.NotNull(proofSkip);
        Assert.Equal(3, proofSkip!.LineOneBased);
    }
}
