using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class LemmaDatabaseTests
{
    [Fact]
    public void TryAddLemma_IndexesTheoremOnly_SkipsDefinitionAndEmptyText()
    {
        var database = new LemmaDatabase(TestInjectedLogger.CreateFatalOnly());
        var pathA = new RelativePath("A.v", new AbsolutePath(Environment.CurrentDirectory));

        Assert.True(database.TryAddLemma(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Theorem,
                "plus_comm",
                text: "Lemma plus_comm : forall n m, n + m = m + n.")));
        Assert.False(database.TryAddLemma(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Definition,
                "foo",
                text: "Definition foo := 1.")));
        Assert.False(database.TryAddLemma(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Theorem,
                "empty",
                text: "   ")));
        Assert.False(database.TryAddLemma(
            pathA,
            _Sentence(
                CoqSentenceVernacType.Other,
                "req",
                text: "Require Import List.")));

        var page = database.GetLemmasInFile(pathA, offset: 0, maxMatches: 10);
        Assert.Equal(1, page.TotalLemmaCount);
        Assert.Single(page.Hits);
        Assert.Equal("Lemma plus_comm : forall n m, n + m = m + n.", page.Hits[0].Text);
    }

    [Fact]
    public void GetLemmasInFile_RespectsOffsetAndMaxMatches()
    {
        var database = new LemmaDatabase(TestInjectedLogger.CreateFatalOnly());
        var path = new RelativePath("T.v", new AbsolutePath(Environment.CurrentDirectory));

        Assert.True(database.TryAddLemma(path, _Sentence(CoqSentenceVernacType.Theorem, "a", text: "Lemma a : True.")));
        Assert.True(database.TryAddLemma(path, _Sentence(CoqSentenceVernacType.Theorem, "b", text: "Lemma b : True.")));
        Assert.True(database.TryAddLemma(path, _Sentence(CoqSentenceVernacType.Theorem, "c", text: "Lemma c : True.")));

        var page = database.GetLemmasInFile(path, offset: 1, maxMatches: 1);
        Assert.Equal(3, page.TotalLemmaCount);
        Assert.Single(page.Hits);
        Assert.Equal("Lemma b : True.", page.Hits[0].Text);
    }

    [Fact]
    public void GetLemmasInFile_WhenOtherFile_ReturnsOnlyThatFile()
    {
        var database = new LemmaDatabase(TestInjectedLogger.CreateFatalOnly());
        var pathA = new RelativePath("A.v", new AbsolutePath(Environment.CurrentDirectory));
        var pathB = new RelativePath("B.v", new AbsolutePath(Environment.CurrentDirectory));

        Assert.True(database.TryAddLemma(pathA, _Sentence(CoqSentenceVernacType.Theorem, "a", text: "Lemma a : True.")));
        Assert.True(database.TryAddLemma(pathB, _Sentence(CoqSentenceVernacType.Theorem, "b", text: "Lemma b : True.")));

        var page = database.GetLemmasInFile(pathA, offset: 0, maxMatches: 10);
        Assert.Equal(1, page.TotalLemmaCount);
        Assert.Single(page.Hits);
        Assert.Equal("Lemma a : True.", page.Hits[0].Text);
    }

    private static CoqSentence _Sentence(
        CoqSentenceVernacType vernacType,
        string name,
        string text,
        int startLineOneBased = 1,
        int endLineOneBased = 1)
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
