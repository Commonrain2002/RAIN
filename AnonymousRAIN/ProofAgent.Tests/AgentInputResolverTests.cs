using ProofAgent.Cli;
using Xunit;

namespace ProofAgent.Tests;

public class AgentInputResolverTests
{
    private const string TestLlmApiKey = "test-api-key";

    [Fact]
    public void TryResolveMainTaskInputs_Help_ReturnsFalse()
    {
        var logger = TestInjectedLogger.CreateFatalOnly();
        var resolver = new AgentInputResolver(logger);
        Assert.False(
            resolver.TryResolveMainTaskInputs(["--help"], "{}", "/tmp", TestLlmApiKey, out _));
    }

    [Fact]
    public void TryResolveMainTaskInputs_UnexpectedArgs_ReturnsFalse()
    {
        var logger = TestInjectedLogger.CreateFatalOnly();
        var resolver = new AgentInputResolver(logger);
        Assert.False(
            resolver.TryResolveMainTaskInputs(
                ["--project-root", "/x"],
                "{}",
                "/tmp",
                TestLlmApiKey,
                out _));
    }
}
