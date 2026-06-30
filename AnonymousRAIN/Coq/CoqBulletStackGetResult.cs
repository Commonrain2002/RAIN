namespace ProofAgent.Coq;

public readonly struct CoqBulletStackGetResult
{
    public CoqBulletStackGetResult(
        bool succeeded,
        CoqBulletStack? bulletStack,
        string failureReason)
    {
        Succeeded = succeeded;
        BulletStack = bulletStack;
        FailureReason = failureReason;
    }

    public bool Succeeded { get; }

    public CoqBulletStack? BulletStack { get; }

    public string FailureReason { get; }

    public static CoqBulletStackGetResult FromFailure(string failureReason)
    {
        return new CoqBulletStackGetResult(false, null, failureReason);
    }

    public static CoqBulletStackGetResult FromSuccess(CoqBulletStack bulletStack)
    {
        return new CoqBulletStackGetResult(true, bulletStack, "");
    }
}
