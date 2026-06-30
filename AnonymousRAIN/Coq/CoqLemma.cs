using ProofAgent.Tools;

namespace ProofAgent.Coq;

public class CoqLemma
{
    public required RelativePath RelativePath { get; init; }

    public string Text { get; init; } = "";
}
