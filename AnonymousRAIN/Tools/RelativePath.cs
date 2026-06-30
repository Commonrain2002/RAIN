namespace ProofAgent.Tools;

/// <summary>
/// A path relative to a base directory, normalized once at construction to a POSIX (<c>/</c>-separated) form.
/// The input string may itself be absolute or relative; both are resolved against <paramref name="baseDirectory"/>.
/// </summary>
public class RelativePath : IEquatable<RelativePath>
{
    #region Fields

    private readonly AbsolutePath _BaseDirectory;

    private readonly string _PosixPath;

    #endregion Fields

    #region Properties

    /// <summary>Base directory this path is relative to.</summary>
    public AbsolutePath BaseDirectory => _BaseDirectory;

    /// <summary>Normalized relative path using <c>/</c> separators (may begin with <c>..</c> when it escapes the base).</summary>
    public string PosixPath => _PosixPath;

    /// <summary>True when the normalized path leaves <see cref="BaseDirectory"/> (begins with <c>..</c>).</summary>
    public bool EscapesBase =>
        _PosixPath == ".."
        || _PosixPath.StartsWith("../", StringComparison.Ordinal);

    #endregion Properties

    public RelativePath(string path, AbsolutePath baseDirectory)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("path must not be empty.", nameof(path));
        }

        _BaseDirectory = baseDirectory ?? throw new ArgumentNullException(nameof(baseDirectory));
        _PosixPath = _NormalizeToPosixRelative(path, baseDirectory);
    }

    /// <summary>Resolve to an absolute path under <see cref="BaseDirectory"/>.</summary>
    public AbsolutePath ToAbsolute()
    {
        var hostRelative = _PosixPath.Replace('/', Path.DirectorySeparatorChar);
        return new AbsolutePath(Path.Combine(_BaseDirectory.FullPath, hostRelative));
    }

    public bool Equals(RelativePath? other)
    {
        return other != null
            && _BaseDirectory.Equals(other._BaseDirectory)
            && string.Equals(_PosixPath, other._PosixPath, StringComparison.Ordinal);
    }

    public override bool Equals(object? obj)
    {
        return Equals(obj as RelativePath);
    }

    public override int GetHashCode()
    {
        return HashCode.Combine(_BaseDirectory, StringComparer.Ordinal.GetHashCode(_PosixPath));
    }

    public override string ToString()
    {
        return _PosixPath;
    }

    #region Private Methods

    private static string _NormalizeToPosixRelative(string path, AbsolutePath baseDirectory)
    {
        var posix = path.Trim().Replace('\\', '/');
        if (posix.StartsWith("./", StringComparison.Ordinal))
        {
            posix = posix[2..];
        }

        if (string.IsNullOrWhiteSpace(posix))
        {
            throw new ArgumentException("path must not be empty.", nameof(path));
        }

        var fullPath = Path.IsPathRooted(posix)
            ? Path.GetFullPath(posix.Replace('/', Path.DirectorySeparatorChar))
            : Path.GetFullPath(Path.Combine(baseDirectory.FullPath, posix));

        return Path.GetRelativePath(baseDirectory.FullPath, fullPath).Replace('\\', '/');
    }

    #endregion Private Methods
}
