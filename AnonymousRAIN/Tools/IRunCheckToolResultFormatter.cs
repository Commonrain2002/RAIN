using ProofAgent.Coq;

namespace ProofAgent.Tools;

public interface IRunCheckToolResultFormatter
{
    string FormatRunCheckFailures(IReadOnlyList<CoqRunCheckFailure> failures);
}
