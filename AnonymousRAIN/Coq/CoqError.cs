using ProofAgent.Tools;

namespace ProofAgent.Coq;

public record CoqError(
    RelativePath? RelativeFilePath,
    int Line,
    int Column,
    string Message)
{
    public override string ToString()
    {
        var file = RelativeFilePath?.PosixPath;
        var shown = string.IsNullOrWhiteSpace(file) ? "(unknown file)" : file;
        return $"File \"{shown}\", line {Line}, character {Column}: {Message}";
    }
}
