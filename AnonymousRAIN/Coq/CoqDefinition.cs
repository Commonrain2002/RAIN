namespace ProofAgent.Coq;

public class CoqDefinition
{
    public string RelativeCoqFilePath { get; init; } = "";

    public int StartLineOneBased { get; init; }

    public int EndLineOneBased { get; init; }

    public string Text { get; init; } = "";
}
