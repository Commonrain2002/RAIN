namespace ProofAgent.Llm;

public class ToolCall
{
    #region Fields

    private readonly string _ToolCallID;

    private readonly string _Name;

    private readonly string _Arguments;

    #endregion Fields

    #region Properties

    public string ToolCallID => _ToolCallID;

    public string Name => _Name;

    public string Arguments => _Arguments;

    #endregion Properties

    public ToolCall(string toolCallID, string name, string arguments)
    {
        _ToolCallID = toolCallID;
        _Name = name;
        _Arguments = arguments;
    }
}
