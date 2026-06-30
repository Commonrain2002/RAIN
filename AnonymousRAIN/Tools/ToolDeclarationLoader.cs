using System.Text.Json;

using ProofAgent.Agent;

namespace ProofAgent.Tools;

public class ToolDeclarationLoader
{
    #region Fields

    private readonly IPromptTextSource _PromptTextSource;

    private readonly Dictionary<string, JsonElement> _Cache = new(StringComparer.Ordinal);

    #endregion Fields

    public ToolDeclarationLoader(IPromptTextSource promptTextSource)
    {
        _PromptTextSource = promptTextSource ?? throw new ArgumentNullException(nameof(promptTextSource));
    }

    public JsonElement GetDeclaration(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath))
        {
            throw new ArgumentException("Relative path is required.", nameof(relativePath));
        }

        var normalizedKey = relativePath.Replace('\\', '/');
        if (_Cache.TryGetValue(normalizedKey, out var cached))
        {
            return cached;
        }

        var json = _PromptTextSource.GetText(normalizedKey);
        using var document = JsonDocument.Parse(json);
        var clone = document.RootElement.Clone();
        _Cache[normalizedKey] = clone;
        return _Cache[normalizedKey];
    }
}
