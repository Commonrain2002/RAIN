using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests.Fakes;

public class QueueCoqProjectChecker : ICoqChecker
{
    #region Fields

    private readonly Queue<CoqCheck> _Results;

    #endregion Fields

    public QueueCoqProjectChecker(IEnumerable<CoqCheck> resultsInCallOrder)
    {
        _Results = new Queue<CoqCheck>(resultsInCallOrder ?? throw new ArgumentNullException(nameof(resultsInCallOrder)));
    }

    public Task<CoqCheck> CheckAsync(
        RelativePath? targetFileRelativePath,
        int timeoutSeconds,
        string command,
        CancellationToken cancellationToken)
    {
        if (_Results.Count == 0)
        {
            throw new InvalidOperationException("QueueCoqProjectChecker: no more queued CheckAsync results.");
        }

        return Task.FromResult(_Results.Dequeue());
    }
}
