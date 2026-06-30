using ProofAgent.Tools;

namespace ProofAgent.Coq;

/// <summary>Runs a project-level Coq check for a target file.</summary>
public interface ICoqChecker
{
    Task<CoqCheck> CheckAsync(
        RelativePath? targetFileRelativePath,
        int timeoutSeconds,
        string command,
        CancellationToken cancellationToken);
}
