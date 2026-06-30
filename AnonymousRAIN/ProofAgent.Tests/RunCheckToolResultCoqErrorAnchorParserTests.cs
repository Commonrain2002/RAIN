using ProofAgent.Session;
using Xunit;

namespace ProofAgent.Tests;

public class RunCheckToolResultCoqErrorAnchorParserTests
{
    [Fact]
    public void TryParse_StandardRunCheckToolSections_ReadsLineAndCharacter()
    {
        const string toolBody = """
            Result: proof check failed.

            ## Coq Error Message
            File "./backend/Locations.v", line 552, character 20: Expects a disjunctive pattern with 0 branches.

            ## Error line around
            (none)

            ## Environment before error
            (none)
            """;

        var parser = new RunCheckToolResultCoqErrorAnchorParser();
        var ok = parser.TryParse(toolBody, out var anchor);

        Assert.True(ok);
        Assert.Equal(552, anchor.LineOneBased);
        Assert.Equal(20, anchor.ColumnZeroBased);
    }

    [Fact]
    public void TryParse_MissingErrorLineSection_ReturnsFalse()
    {
        const string toolBody = """
            ## Coq Error Message
            File "A.v", line 1, character 0: err
            """;

        var parser = new RunCheckToolResultCoqErrorAnchorParser();
        Assert.False(parser.TryParse(toolBody, out _));
    }
}
