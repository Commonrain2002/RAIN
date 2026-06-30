using ProofAgent.Llm;

namespace ProofAgent.Session;

public class LlmSessionUsageReport
{
    #region Fields

    private readonly LlmUsage _ResponseUsage;

    private readonly LlmUsage _SessionCumulativeUsage;

    private readonly bool _EnableReasoning;

    private readonly string _ReasoningEffort;

    private readonly int _Round;

    private readonly int _MaxToolRounds;

    #endregion Fields

    #region Properties

    public LlmUsage ResponseUsage => _ResponseUsage;

    public LlmUsage SessionCumulativeUsage => _SessionCumulativeUsage;

    public bool EnableReasoning => _EnableReasoning;

    public string ReasoningEffort => _ReasoningEffort;

    public int Round => _Round;

    public int MaxToolRounds => _MaxToolRounds;

    #endregion Properties

    public LlmSessionUsageReport(
        LlmUsage responseUsage,
        LlmUsage sessionCumulativeUsage,
        bool enableReasoning,
        string reasoningEffort,
        int round,
        int maxToolRounds)
    {
        _ResponseUsage = responseUsage;
        _SessionCumulativeUsage = sessionCumulativeUsage;
        _EnableReasoning = enableReasoning;
        _ReasoningEffort = reasoningEffort;
        _Round = round;
        _MaxToolRounds = maxToolRounds;
    }
}
