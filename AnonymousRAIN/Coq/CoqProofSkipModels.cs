namespace ProofAgent.Coq;

/// <summary>Per-sentence proof skip/termination commands matched in source (outside comments/strings).</summary>
public enum CoqProofSkipType
{
    Admitted,

    Abort
}

/// <summary>Position of first matched skip sentence in target .v (1-based line, 0-based column, same as <see cref="CoqError"/>).</summary>
public record CoqProofSkip(int LineOneBased, int ColumnZeroBased, CoqProofSkipType Type);
