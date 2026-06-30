namespace ProofAgent.Coq;

public interface ICoqMultiErrorChecker
{
    Task<IReadOnlyList<CoqRunCheckFailure>> RunMultiErrorCheckAsync(CancellationToken cancellationToken);
}
