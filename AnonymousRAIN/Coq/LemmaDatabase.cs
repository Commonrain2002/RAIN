using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

public class LemmaDatabase
{
    #region Fields

    private readonly Dictionary<RelativePath, List<CoqLemma>> _LemmasByRelativePath;

    #endregion Fields

    public LemmaDatabase(ILogger logger)
    {
        if (logger == null)
        {
            throw new ArgumentNullException(nameof(logger));
        }

        _LemmasByRelativePath = new Dictionary<RelativePath, List<CoqLemma>>();
    }

    public bool TryAddLemma(RelativePath relativePath, CoqSentence sentence)
    {
        if (relativePath == null)
        {
            throw new ArgumentNullException(nameof(relativePath));
        }

        if (sentence == null)
        {
            throw new ArgumentNullException(nameof(sentence));
        }

        if (sentence.VernacType != CoqSentenceVernacType.Theorem)
        {
            return false;
        }

        if (string.IsNullOrWhiteSpace(sentence.Text))
        {
            return false;
        }

        if (!_LemmasByRelativePath.TryGetValue(relativePath, out var lemmasInFile))
        {
            lemmasInFile = new List<CoqLemma>();
            _LemmasByRelativePath[relativePath] = lemmasInFile;
        }

        lemmasInFile.Add(new CoqLemma
        {
            RelativePath = relativePath,
            Text = sentence.Text
        });
        return true;
    }

    public CoqLemmaPage GetLemmasInFile(RelativePath relativePath, int offset, int maxMatches)
    {
        if (relativePath == null)
        {
            throw new ArgumentNullException(nameof(relativePath));
        }

        if (offset < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(offset));
        }

        if (maxMatches <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxMatches));
        }

        if (!_LemmasByRelativePath.TryGetValue(relativePath, out var lemmasInFile))
        {
            return new CoqLemmaPage(Array.Empty<CoqLemma>(), 0);
        }

        var chosenLemmas = new List<CoqLemma>();
        var totalLemmaCount = lemmasInFile.Count;
        for (var index = offset; index < lemmasInFile.Count && chosenLemmas.Count < maxMatches; index++)
        {
            chosenLemmas.Add(lemmasInFile[index]);
        }

        return new CoqLemmaPage(chosenLemmas, totalLemmaCount);
    }
}
