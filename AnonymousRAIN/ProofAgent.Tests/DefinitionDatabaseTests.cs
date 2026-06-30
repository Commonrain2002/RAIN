using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class DefinitionDatabaseTests
{
    [Fact]
    public void TryGetDefinition_WhenEmpty_ReturnsFalseAndEmptyList()
    {
        var database = new DefinitionDatabase(TestInjectedLogger.CreateFatalOnly());

        var found = database.TryGetDefinition("foo", out var definitions);

        Assert.False(found);
        Assert.Empty(definitions);
    }

    [Fact]
    public void TryAddDefinition_IndexesDefinitionFixpointAndInductive_SkipsTheoremAndWhitespaceName()
    {
        var database = new DefinitionDatabase(TestInjectedLogger.CreateFatalOnly());
        var pathA = new RelativePath("A.v", new AbsolutePath(Environment.CurrentDirectory));
        var pathB = new RelativePath("B.v", new AbsolutePath(Environment.CurrentDirectory));

        Assert.True(database.TryAddDefinition(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Definition,
                "foo",
                startLineOneBased: 1,
                endLineOneBased: 1,
                text: "Definition foo := 1.")));
        Assert.False(database.TryAddDefinition(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Theorem,
                "ignoredTheorem",
                startLineOneBased: 2,
                endLineOneBased: 2,
                text: "Theorem ignoredTheorem : True.")));
        Assert.False(database.TryAddDefinition(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Definition,
                "   ",
                startLineOneBased: 3,
                endLineOneBased: 3,
                text: "Definition   := 0.")));
        Assert.True(database.TryAddDefinition(
            pathB,
            _Sentence(
                CoqSentenceVernacType.Inductive,
                "bar",
                startLineOneBased: 10,
                endLineOneBased: 12,
                text: "Inductive bar : Set.")));
        Assert.True(database.TryAddDefinition(
            pathB,
            _Sentence(
                CoqSentenceVernacType.Fixpoint,
                "fp",
                startLineOneBased: 20,
                endLineOneBased: 22,
                text: "Fixpoint fp (n : nat) : nat := n.")));
        Assert.False(database.TryAddDefinition(
            pathB,
            _Sentence(
                CoqSentenceVernacType.Other,
                "other",
                startLineOneBased: 30,
                endLineOneBased: 30,
                text: "Require Import List.")));

        Assert.True(database.TryGetDefinition("foo", out var fooDefinitions));
        Assert.Single(fooDefinitions);
        Assert.Equal("A.v", fooDefinitions[0].RelativeCoqFilePath);
        Assert.Equal(1, fooDefinitions[0].StartLineOneBased);
        Assert.Equal(1, fooDefinitions[0].EndLineOneBased);
        Assert.Equal("Definition foo := 1.", fooDefinitions[0].Text);

        Assert.True(database.TryGetDefinition("bar", out var barDefinitions));
        Assert.Single(barDefinitions);
        Assert.Equal("B.v", barDefinitions[0].RelativeCoqFilePath);
        Assert.Equal(10, barDefinitions[0].StartLineOneBased);
        Assert.Equal(12, barDefinitions[0].EndLineOneBased);

        Assert.True(database.TryGetDefinition("fp", out var fpDefinitions));
        Assert.Single(fpDefinitions);

        Assert.False(database.TryGetDefinition("ignoredTheorem", out var theoremHits));
        Assert.Empty(theoremHits);
        Assert.False(database.TryGetDefinition("other", out var otherHits));
        Assert.Empty(otherHits);
    }

    [Fact]
    public void TryGetDefinition_WhenSameNameInMultipleFiles_ReturnsAllEntries()
    {
        var database = new DefinitionDatabase(TestInjectedLogger.CreateFatalOnly());
        var pathX = new RelativePath("X.v", new AbsolutePath(Environment.CurrentDirectory));
        var pathY = new RelativePath("Y.v", new AbsolutePath(Environment.CurrentDirectory));

        Assert.True(database.TryAddDefinition(
            pathX,
            _Sentence(CoqSentenceVernacType.Definition, "dup", 1, 1, "Definition dup := 1.")));
        Assert.True(database.TryAddDefinition(
            pathY,
            _Sentence(CoqSentenceVernacType.Definition, "dup", 5, 7, "Definition dup := 2.")));

        Assert.True(database.TryGetDefinition("dup", out var definitions));
        Assert.Equal(2, definitions.Count);
        Assert.Contains(definitions, d => d.RelativeCoqFilePath == "X.v" && d.Text == "Definition dup := 1.");
        Assert.Contains(definitions, d => d.RelativeCoqFilePath == "Y.v" && d.Text == "Definition dup := 2.");
    }

    [Fact]
    public void TryGetDefinition_WhenNameMissing_ReturnsFalseAndEmptyList()
    {
        var database = new DefinitionDatabase(TestInjectedLogger.CreateFatalOnly());

        var found = database.TryGetDefinition("missing", out var definitions);

        Assert.False(found);
        Assert.Empty(definitions);
    }

    private static CoqSentence _Sentence(
        CoqSentenceVernacType vernacType,
        string name,
        int startLineOneBased,
        int endLineOneBased,
        string text)
    {
        return new CoqSentence
        {
            VernacType = vernacType,
            Name = name,
            StartLineOneBased = startLineOneBased,
            EndLineOneBased = endLineOneBased,
            Text = text,
        };
    }
}
