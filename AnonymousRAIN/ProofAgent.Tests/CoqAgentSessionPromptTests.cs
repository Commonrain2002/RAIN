using ProofAgent.Agent;
using Xunit;

namespace ProofAgent.Tests;

public class CoqAgentSessionPromptTests
{
    [Fact]
    public void CoqProofSystemPromptFile_ContainsHardConstraintsAndCoq()
    {
        var text = PromptTestFixtures.CreatePromptTextSource(TestInjectedLogger.CreateFatalOnly()).GetText("Agent/CoqProofSystem.txt").TrimEnd();

        Assert.Contains("## Coq Proof Hint", text, StringComparison.Ordinal);
        Assert.Contains("search tools", text, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("read_lemma", text, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("lia instead", text, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("## SSReflect syntax and semantics", text, StringComparison.Ordinal);
    }

    [Fact]
    public void CoqProofSsreflectPromptFile_ContainsSsreflectGuidance()
    {
        var text = PromptTestFixtures.CreatePromptTextSource(TestInjectedLogger.CreateFatalOnly()).GetText("Agent/CoqProofSsreflect.txt").TrimEnd();

        Assert.Contains("## SSReflect syntax and semantics", text, StringComparison.Ordinal);
        Assert.Contains("Locked subterms", text, StringComparison.Ordinal);
        Assert.Contains("SSReflect worked examples", text, StringComparison.Ordinal);
        Assert.Contains("elim: n.", text, StringComparison.Ordinal);
    }

    [Fact]
    public void KnowledgeCollectionPrompt_AppendsLemmaSection()
    {
        var template = PromptTestFixtures.CreatePromptTextSource(TestInjectedLogger.CreateFatalOnly()).GetText("Agent/KnowledgeCollectionPrompt.txt");
        var knowledgeSection = "## Definitions helpful for the proof" + Environment.NewLine + Environment.NewLine + "Lemma: plus_comm.";
        var text = template
            .Replace("{{InitialUserMessage}}", "Task body", StringComparison.Ordinal)
            .Replace("{{KnowledgeCollectionAssistantText}}", knowledgeSection, StringComparison.Ordinal)
            .TrimEnd();

        Assert.Contains("Task body", text, StringComparison.Ordinal);
        Assert.Contains("## Definitions helpful for the proof", text, StringComparison.Ordinal);
        Assert.Contains("Lemma: plus_comm.", text, StringComparison.Ordinal);
    }

    [Fact]
    public void NoKnowledgeCollectionPrompt_ReturnsInitialOnly()
    {
        var template = PromptTestFixtures.CreatePromptTextSource(TestInjectedLogger.CreateFatalOnly()).GetText("Agent/NoKnowledgeCollectionPrompt.txt");
        var text = template
            .Replace("{{InitialUserMessage}}", "Task", StringComparison.Ordinal)
            .TrimEnd();

        Assert.Equal("Task", text);
    }
}
