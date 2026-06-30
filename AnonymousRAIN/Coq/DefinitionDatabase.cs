using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

public class DefinitionDatabase
{
    #region Fields

    private Dictionary<string, List<CoqDefinition>> _DefinitionsByName;

    #endregion Fields

    public DefinitionDatabase(ILogger logger)
    {
        if (logger == null)
        {
            throw new ArgumentNullException(nameof(logger));
        }

        _DefinitionsByName = new Dictionary<string, List<CoqDefinition>>(StringComparer.Ordinal);
    }

    public bool TryAddDefinition(RelativePath relativeCoqFilePath, CoqSentence sentence)
    {
        if (relativeCoqFilePath == null)
        {
            throw new ArgumentNullException(nameof(relativeCoqFilePath));
        }

        if (sentence == null)
        {
            throw new ArgumentNullException(nameof(sentence));
        }

        if (!_IsDefinitionSentence(sentence))
        {
            return false;
        }

        var definitionName = sentence.Name.Trim();
        if (definitionName.Length == 0)
        {
            return false;
        }

        var coqDefinition = _CreateCoqDefinition(relativeCoqFilePath, sentence);
        _AddDefinition(_DefinitionsByName, definitionName, coqDefinition);
        return true;
    }

    public bool TryGetDefinition(string name, out IReadOnlyList<CoqDefinition> definitions)
    {
        if (name == null)
        {
            throw new ArgumentNullException(nameof(name));
        }

        if (_DefinitionsByName.TryGetValue(name, out var definitionList))
        {
            definitions = definitionList;
            return true;
        }

        definitions = Array.Empty<CoqDefinition>();
        return false;
    }

    #region Private Methods

    private static bool _IsDefinitionSentence(CoqSentence sentence)
    {
        return sentence.VernacType == CoqSentenceVernacType.Definition
            || sentence.VernacType == CoqSentenceVernacType.Fixpoint
            || sentence.VernacType == CoqSentenceVernacType.Inductive;
    }

    private static CoqDefinition _CreateCoqDefinition(RelativePath relativePath, CoqSentence sentence)
    {
        return new CoqDefinition
        {
            RelativeCoqFilePath = relativePath.PosixPath,
            StartLineOneBased = sentence.StartLineOneBased,
            EndLineOneBased = sentence.EndLineOneBased,
            Text = sentence.Text
        };
    }

    private static void _AddDefinition(
        Dictionary<string, List<CoqDefinition>> definitionsByName,
        string definitionName,
        CoqDefinition coqDefinition)
    {
        if (!definitionsByName.TryGetValue(definitionName, out var definitions))
        {
            definitions = new List<CoqDefinition>();
            definitionsByName[definitionName] = definitions;
        }

        definitions.Add(coqDefinition);
    }

    #endregion Private Methods
}
