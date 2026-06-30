namespace ProofAgent.Coq;

/// <summary>Supplies Coq environment text shown alongside a run_check failure.</summary>
public interface ICoqEnvironmentCapturer
{
    Task<string> GetEnvironmentTextAsync(
        CoqError error,
        CancellationToken cancellationToken);
}
