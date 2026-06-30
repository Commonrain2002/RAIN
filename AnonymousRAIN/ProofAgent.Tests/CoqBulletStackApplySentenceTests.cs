using ProofAgent.Coq;
using Xunit;

namespace ProofAgent.Tests;

public class CoqBulletStackApplySentenceTests
{
    [Fact]
    public void ApplySentence_DashPlusPlusDash_CollapsesToSingleDashAboveRoot()
    {
        var stack = CoqBulletStack.CreateForBackwardBuild();
        _ApplyBulletTokens(stack, "-", "+", "+", "-");

        Assert.Equal(new[] { "{", "-" }, _TokenSpine(stack));
    }

    [Fact]
    public void ApplySentence_DashOpenDash_KeepsThreeLevelSpine()
    {
        var stack = CoqBulletStack.CreateForBackwardBuild();
        _ApplyBulletTokens(stack, "-", "{", "-");

        Assert.Equal(new[] { "{", "-", "{", "-" }, _TokenSpine(stack));
    }

    [Fact]
    public void ApplySentence_ComplexCurlyAndBullets_MatchesExpectedSpine()
    {
        var stack = CoqBulletStack.CreateForBackwardBuild();
        _ApplyBulletTokens(stack, "-", "+", "+", "*", "{", "+", "}", "*");

        Assert.Equal(new[] { "{", "-", "+", "*" }, _TokenSpine(stack));
    }

    private static void _ApplyBulletTokens(CoqBulletStack stack, params string[] tokens)
    {
        for (var i = 0; i < tokens.Length; i++)
        {
            var token = tokens[i];
            var classification = token is "{" or "}"
                ? CoqSentenceClassification.Curly
                : CoqSentenceClassification.Bullet;
            var sentence = new CoqSentence
            {
                Index = i,
                Text = token,
                Classification = classification,
            };
            Assert.True(stack.ApplySentence(sentence));
        }
    }

    private static string[] _TokenSpine(CoqBulletStack stack)
    {
        return stack.Cells.Select(static c => c.TrimmedToken).ToArray();
    }
}
