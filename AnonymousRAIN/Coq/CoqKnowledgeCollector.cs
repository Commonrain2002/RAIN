using Serilog;

namespace ProofAgent.Coq;

public class CoqKnowledgeCollector
{
    #region Fields

    private const int _MinDefinitionCountBeforeTextExpansion = 3;

    private const int _MaxDefinitionsReturned = 30;

    private readonly DefinitionDatabase _DefinitionDatabase;

    private readonly ILogger _Logger;

    #endregion Fields

    public CoqKnowledgeCollector(DefinitionDatabase definitionDatabase, ILogger logger)
    {
        _DefinitionDatabase = definitionDatabase ?? throw new ArgumentNullException(nameof(definitionDatabase));
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public IReadOnlyList<CoqDefinition> GetDefinitions(IReadOnlyList<CoqRunCheckFailure> failures)
    {
        if (failures == null)
        {
            throw new ArgumentNullException(nameof(failures));
        }

        var definitions = new List<CoqDefinition>();
        var definitionKeys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var failure in failures)
        {
            _CollectDefinitionsFromText(failure.EnvironmentText, definitions, definitionKeys);
        }

        if (definitions.Count < _MinDefinitionCountBeforeTextExpansion)
        {
            var definitionTexts = definitions.Select(definition => definition.Text).ToArray();
            foreach (var definitionText in definitionTexts)
            {
                _CollectDefinitionsFromText(definitionText, definitions, definitionKeys);
            }
        }

        var selectedDefinitions = definitions.Take(_MaxDefinitionsReturned).ToArray();
        _Logger.Information(
            "coq_knowledge_collector: selected {DefinitionCount} definitions from {FailureCount} failures.",
            selectedDefinitions.Length,
            failures.Count);
        foreach (var definition in selectedDefinitions)
        {
            _Logger.Information(
                "coq_knowledge_collector: selected {RelativePath}:{StartLine}-{EndLine}.",
                definition.RelativeCoqFilePath,
                definition.StartLineOneBased,
                definition.EndLineOneBased);
        }

        return selectedDefinitions;
    }

    #region Private Methods

    private void _CollectDefinitionsFromText(
        string text,
        List<CoqDefinition> definitions,
        HashSet<string> definitionKeys)
    {
        foreach (var token in _SplitByWhitespace(text))
        {
            var normalizedToken = _TrimTokenBoundaryPunctuation(token);
            if (normalizedToken.Length == 0)
            {
                continue;
            }

            if (!_DefinitionDatabase.TryGetDefinition(normalizedToken, out var matchedDefinitions))
            {
                continue;
            }

            if (!_TryAppendMatchedDefinitions(matchedDefinitions, definitions, definitionKeys))
            {
                return;
            }
        }
    }

    private static string[] _SplitByWhitespace(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return Array.Empty<string>();
        }

        return text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
    }

    private static string _TrimTokenBoundaryPunctuation(string token)
    {
        if (string.IsNullOrEmpty(token))
        {
            return string.Empty;
        }

        var start = 0;
        var end = token.Length - 1;
        while (start <= end && !_IsDefinitionTokenChar(token[start]))
        {
            start++;
        }

        while (end >= start && !_IsDefinitionTokenChar(token[end]))
        {
            end--;
        }

        return start > end ? string.Empty : token[start..(end + 1)];
    }

    private static bool _IsDefinitionTokenChar(char value)
    {
        return char.IsLetterOrDigit(value) || value is '_' or '\'';
    }

    private bool _TryAppendMatchedDefinitions(
        IReadOnlyList<CoqDefinition> matchedDefinitions,
        List<CoqDefinition> definitions,
        HashSet<string> definitionKeys)
    {
        foreach (var matchedDefinition in matchedDefinitions)
        {
            if (definitions.Count >= _MaxDefinitionsReturned)
            {
                return false;
            }

            var definitionKey = _BuildDefinitionKey(matchedDefinition);
            if (!definitionKeys.Add(definitionKey))
            {
                continue;
            }

            definitions.Add(matchedDefinition);
        }

        return true;
    }

    private static string _BuildDefinitionKey(CoqDefinition definition)
    {
        return $"{definition.RelativeCoqFilePath}:{definition.StartLineOneBased}:{definition.EndLineOneBased}";
    }

    #endregion Private Methods
}
