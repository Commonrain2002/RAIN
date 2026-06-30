using System.Text.Json;

namespace ProofAgent.Tools;

public class ToolRegistry
{
    #region Fields

    private readonly IReadOnlyDictionary<string, ITool> _NameToTool;

    #endregion Fields

    public ToolRegistry(IEnumerable<ITool> tools)
    {
        var list = tools.ToList();
        var duplicates = list.GroupBy(static t => t.Name).Where(static g => g.Count() > 1).Select(static g => g.Key).ToList();
        if (duplicates.Count > 0)
        {
            throw new ArgumentException($"Duplicate tool names: {string.Join(", ", duplicates)}");
        }

        _NameToTool = list.ToDictionary(static t => t.Name, static t => t, StringComparer.Ordinal);
    }

    public IReadOnlyList<JsonElement> GetDeclarations()
    {
        return _NameToTool.Values.Select(static t => t.GetDeclaration()).ToList();
    }

    public async Task<string> RunAsync(
        IToolExecutionContext context,
        string toolName,
        JsonElement arguments,
        CancellationToken cancellationToken)
    {
        if (!_NameToTool.TryGetValue(toolName, out var tool))
        {
            return $"Unknown tool: {toolName}";
        }

        return await tool.RunAsync(context, arguments, cancellationToken).ConfigureAwait(false);
    }
}
