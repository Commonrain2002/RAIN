namespace ProofAgent.Tools;

/// <summary>
/// An absolute filesystem path, normalized once at construction via <see cref="Path.GetFullPath(string)"/>.
/// Carries no filesystem access; use <see cref="ProjectFileSystem"/> for IO.
/// </summary>
public class AbsolutePath : IEquatable<AbsolutePath>
{
    #region Fields

    private readonly string _FullPath;

    #endregion Fields

    #region Properties

    /// <summary>Normalized absolute path using the host directory separator.</summary>
    public string FullPath => _FullPath;

    #endregion Properties

    public AbsolutePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("path must not be empty.", nameof(path));
        }

        _FullPath = Path.GetFullPath(path.Trim());
    }

    /// <summary>True when this path equals <paramref name="ancestor"/> or resides anywhere beneath it.</summary>
    public bool IsUnder(AbsolutePath ancestor)
    {
        if (ancestor == null)
        {
            throw new ArgumentNullException(nameof(ancestor));
        }

        var relative = Path.GetRelativePath(ancestor.FullPath, _FullPath);
        if (relative == ".")
        {
            return true;
        }

        return !_RelativeEscapes(relative);
    }

    public bool Equals(AbsolutePath? other)
    {
        return other != null && string.Equals(_FullPath, other._FullPath, StringComparison.Ordinal);
    }

    public override bool Equals(object? obj)
    {
        return Equals(obj as AbsolutePath);
    }

    public override int GetHashCode()
    {
        return StringComparer.Ordinal.GetHashCode(_FullPath);
    }

    public override string ToString()
    {
        return _FullPath;
    }

    #region Private Methods

    private static bool _RelativeEscapes(string relative)
    {
        return relative == ".."
            || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            || relative.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal)
            || Path.IsPathRooted(relative);
    }

    #endregion Private Methods
}
