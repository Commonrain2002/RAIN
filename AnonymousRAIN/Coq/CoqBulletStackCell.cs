namespace ProofAgent.Coq;

public class CoqBulletStackCell
{
    public CoqBulletStackCell(string trimmedToken, ulong cellIdentity)
    {
        TrimmedToken = trimmedToken;
        CellIdentity = cellIdentity;
    }

    public string TrimmedToken { get; }

    public ulong CellIdentity { get; }
}
