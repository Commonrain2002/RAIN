using ProofAgent.Coq;

namespace ProofAgent.Tests.Fakes;

public class FixedCoqEnvironmentTextSource : ICoqEnvironmentCapturer
{
    #region Fields

    private readonly string _EnvironmentText;

    #endregion Fields

    public FixedCoqEnvironmentTextSource(string environmentText)
    {
        _EnvironmentText = environmentText ?? throw new ArgumentNullException(nameof(environmentText));
    }

    public Task<string> GetEnvironmentTextAsync(
        CoqError error,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(_EnvironmentText);
    }
}
