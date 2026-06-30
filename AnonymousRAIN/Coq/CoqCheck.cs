namespace ProofAgent.Coq;

public record CoqCheck(
    CoqCheckType Type,
    CoqError? Error,
    string RawOutput,
    int TimeoutSeconds)
{
    public bool Success => Type == CoqCheckType.Success;

    public bool TimedOut => Type == CoqCheckType.TimedOut;
}

