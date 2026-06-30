using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

public class UnconfiguredCoqSentenceSplitter : ICoqSentenceSplitter
{
    #region Fields

    private readonly ILogger _Logger;

    #endregion Fields

    public UnconfiguredCoqSentenceSplitter(ILogger logger)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public Task<IReadOnlyList<CoqSentence>> SplitAsync(RelativePath relativeCoqFilePath, CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        _Logger.Warning(
            "parse-sentence-script: not configured. No external script was invoked. Target={Target}",
            relativeCoqFilePath.PosixPath);
        return Task.FromResult<IReadOnlyList<CoqSentence>>(Array.Empty<CoqSentence>());
    }
}
