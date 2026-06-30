namespace ProofAgent.Session;

public class RunCheckToolResultCoqErrorAnchor
{
    #region Fields

    private readonly int _LineOneBased;

    private readonly int _ColumnZeroBased;

    #endregion Fields

    #region Properties

    public int LineOneBased => _LineOneBased;

    public int ColumnZeroBased => _ColumnZeroBased;

    #endregion Properties

    public RunCheckToolResultCoqErrorAnchor(int lineOneBased, int columnZeroBased)
    {
        if (lineOneBased <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(lineOneBased));
        }

        if (columnZeroBased < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(columnZeroBased));
        }

        _LineOneBased = lineOneBased;
        _ColumnZeroBased = columnZeroBased;
    }
}
