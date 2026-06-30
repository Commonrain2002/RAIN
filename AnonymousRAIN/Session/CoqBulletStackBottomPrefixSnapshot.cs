using ProofAgent.Coq;

namespace ProofAgent.Session;

public class CoqBulletStackBottomPrefixSnapshot
{
    #region Fields

    private readonly ulong[] _CellIdentities;

    #endregion Fields

    public CoqBulletStackBottomPrefixSnapshot(IReadOnlyList<ulong> cellIdentities)
    {
        ArgumentNullException.ThrowIfNull(cellIdentities);
        _CellIdentities = cellIdentities.ToArray();
    }

    public bool IdentitiesEqual(CoqBulletStackBottomPrefixSnapshot other)
    {
        ArgumentNullException.ThrowIfNull(other);
        if (_CellIdentities.Length != other._CellIdentities.Length)
        {
            return false;
        }

        for (var i = 0; i < _CellIdentities.Length; i++)
        {
            if (_CellIdentities[i] != other._CellIdentities[i])
            {
                return false;
            }
        }

        return true;
    }

    public string FormatCellIdentitiesForLog()
    {
        if (_CellIdentities.Length == 0)
        {
            return "[]";
        }

        return "[" + string.Join(", ", _CellIdentities) + "]";
    }

    public static CoqBulletStackBottomPrefixSnapshot FromStackCells(
        IReadOnlyList<CoqBulletStackCell> cells,
        int prefixCellCount)
    {
        ArgumentNullException.ThrowIfNull(cells);
        if (prefixCellCount <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(prefixCellCount));
        }

        var count = Math.Min(prefixCellCount, cells.Count);
        var identities = new ulong[count];
        for (var i = 0; i < count; i++)
        {
            identities[i] = cells[i].CellIdentity;
        }

        return new CoqBulletStackBottomPrefixSnapshot(identities);
    }
}
