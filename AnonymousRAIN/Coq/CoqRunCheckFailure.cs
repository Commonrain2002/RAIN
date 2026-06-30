namespace ProofAgent.Coq;

/// <summary>One failed run_check outcome with environment and source context for tool prompt assembly.</summary>
public class CoqRunCheckFailure
{
    public CoqCheck Check { get; init; } = null!;

    public string EnvironmentText { get; init; } = "";

    public string SourceSnippet { get; init; } = "";
}
