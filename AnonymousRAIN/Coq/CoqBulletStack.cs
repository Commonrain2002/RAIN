namespace ProofAgent.Coq;

public class CoqBulletStack
{
    #region Fields

    private const ulong _FirstCellIdentityValue = 1UL;

    private readonly List<CoqBulletStackCell> _Cells;

    private ulong _NextCellID;

    #endregion Fields

    public CoqBulletStack(IReadOnlyList<CoqBulletStackCell> cells)
    {
        ArgumentNullException.ThrowIfNull(cells);
        _Cells = cells is List<CoqBulletStackCell> list
            ? list
            : cells.ToList();

        _NextCellID = _FirstCellIdentityValue;
    }

    private CoqBulletStack(List<CoqBulletStackCell> mutableCells, ulong nextCellId)
    {
        _Cells = mutableCells;
        _NextCellID = nextCellId;
    }

    public IReadOnlyList<CoqBulletStackCell> Cells => _Cells;

    public static CoqBulletStack CreateForBackwardBuild()
    {
        var nextCellId = _FirstCellIdentityValue;
        var rootCell = new CoqBulletStackCell("{", nextCellId++);
        return new CoqBulletStack(new List<CoqBulletStackCell> { rootCell }, nextCellId);
    }

    public CoqBulletStack Clone()
    {
        var copy = _Cells
            .Select(static c => new CoqBulletStackCell(c.TrimmedToken, c.CellIdentity))
            .ToList();
        return new CoqBulletStack(copy, _NextCellID);
    }

    public CoqBulletStack ToSnapshot()
    {
        var snapshot = _Cells
            .Select(static c => new CoqBulletStackCell(c.TrimmedToken, c.CellIdentity))
            .ToList();
        return new CoqBulletStack(snapshot);
    }

    public ulong? GetTopCellIdentity()
    {
        if (_Cells.Count == 0)
        {
            return null;
        }

        return _Cells[^1].CellIdentity;
    }

    public bool ApplySentence(CoqSentence sentence)
    {
        if (!_IsBulletOrCurly(sentence.Classification))
        {
            return true;
        }

        if (_IsProofDotBullet(sentence))
        {
            _ResetToRootBrace();
            return true;
        }

        var token = sentence.Text.Trim();
        return _TryApplyBulletOrCurlyToken(_NormalizeBulletToken(token));
    }

    public bool CheckCellIDInStack(ulong cellID)
    {
        for (var i = _Cells.Count - 1; i >= 0; i--)
        {
            if (_Cells[i].CellIdentity == cellID)
            {
                return true;
            }
        }

        return false;
    }

    #region Private Methods

    private void _ResetToRootBrace()
    {
        _Cells.Clear();
        _Cells.Add(new CoqBulletStackCell("{", _NextCellID++));
    }

    private bool _TryApplyBulletOrCurlyToken(string token)
    {
        if (_IsOpenBrace(token))
        {
            _Cells.Add(new CoqBulletStackCell(token, _NextCellID++));
            return true;
        }

        if (_IsCloseBrace(token))
        {
            return _TryPopMatchingOpenBrace();
        }

        var topBullets = _CollectTopBullets();
        if (topBullets.Contains(token))
        {
            while (_Cells.Count > 1 && _Cells[^1].TrimmedToken != token)
            {
                _Cells.RemoveAt(_Cells.Count - 1);
            }

            if (_Cells.Count <= 1 || _Cells[^1].TrimmedToken != token)
            {
                return false;
            }

            _Cells.RemoveAt(_Cells.Count - 1);
            _Cells.Add(new CoqBulletStackCell(token, _NextCellID++));
            return true;
        }

        _Cells.Add(new CoqBulletStackCell(token, _NextCellID++));
        return true;
    }

    private List<string> _CollectTopBullets()
    {
        var segment = new List<string>();
        for (var i = _Cells.Count - 1; i >= 0; i--)
        {
            if (_Cells[i].TrimmedToken == "{")
            {
                break;
            }

            segment.Add(_Cells[i].TrimmedToken);
        }

        return segment;
    }

    private bool _TryPopMatchingOpenBrace()
    {
        _PopUntilOpenBraceOrEmpty();

        if (_Cells.Count <= 1)
        {
            return false;
        }

        if (_Cells[^1].TrimmedToken != "{")
        {
            return false;
        }

        _Cells.RemoveAt(_Cells.Count - 1);
        return true;
    }

    private void _PopUntilOpenBraceOrEmpty()
    {
        while (_Cells.Count > 1 && _Cells[^1].TrimmedToken != "{")
        {
            _Cells.RemoveAt(_Cells.Count - 1);
        }
    }

    private static string _NormalizeBulletToken(string token)
    {
        if (token.EndsWith("{", StringComparison.Ordinal))
        {
            return "{";
        }

        return token;
    }

    private static bool _IsOpenBrace(string token)
    {
        return token == "{";
    }

    private static bool _IsCloseBrace(string token)
    {
        return token == "}";
    }

    private static bool _IsBulletOrCurly(CoqSentenceClassification classification)
    {
        return classification is CoqSentenceClassification.Bullet
            or CoqSentenceClassification.Curly;
    }

    private static bool _IsBulletClassification(CoqSentenceClassification classification)
    {
        return classification == CoqSentenceClassification.Bullet;
    }

    private static bool _IsProofDotBullet(CoqSentence sentence)
    {
        if (!_IsBulletClassification(sentence.Classification))
        {
            return false;
        }

        return string.Equals(sentence.Text.Trim(), "Proof.", StringComparison.Ordinal);
    }

    #endregion Private Methods
}
