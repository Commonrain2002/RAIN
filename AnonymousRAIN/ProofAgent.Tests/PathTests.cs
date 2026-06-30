using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests;

/// <summary>Test-only helpers for constructing the normalized path types and dependent records.</summary>
public static class PathTests
{
    public static AbsolutePath Abs(string fullPath)
    {
        return new AbsolutePath(fullPath);
    }

    public static RelativePath Rel(this ProjectFileSystem fileSystem, string posixOrRelative)
    {
        return new RelativePath(posixOrRelative, fileSystem.Root);
    }

    public static RelativePath Rel(string posixOrRelative, string baseDirectory)
    {
        return new RelativePath(posixOrRelative, new AbsolutePath(baseDirectory));
    }

    public static RelativePath Rel(string posixOrRelative, AbsolutePath baseDirectory)
    {
        return new RelativePath(posixOrRelative, baseDirectory);
    }

    public static CoqError Error(string? file, int line, int column, string message, string baseDirectory)
    {
        var relative = file == null ? null : new RelativePath(file, new AbsolutePath(baseDirectory));
        return new CoqError(relative, line, column, message);
    }

    public static CoqError Error(string? file, int line, int column, string message)
    {
        return Error(file, line, column, message, Path.GetTempPath());
    }
}
