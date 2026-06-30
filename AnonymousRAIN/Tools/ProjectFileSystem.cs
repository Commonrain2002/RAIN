namespace ProofAgent.Tools;

public class ProjectFileSystem : ReadOnlyFileSystem
{
    #region Fields

    private readonly AbsolutePath _TempRoot;

    private readonly HashSet<AbsolutePath> _OwnedTempPaths;

    #endregion Fields

    public ProjectFileSystem(string projectRoot)
        : base(string.IsNullOrWhiteSpace(projectRoot) ? Environment.CurrentDirectory : projectRoot)
    {
        _TempRoot = new AbsolutePath(Path.GetTempPath());
        _OwnedTempPaths = new HashSet<AbsolutePath>();
    }

    public ProjectFileSystem(AbsolutePath projectRoot)
        : base(projectRoot ?? throw new ArgumentNullException(nameof(projectRoot)))
    {
        _TempRoot = new AbsolutePath(Path.GetTempPath());
        _OwnedTempPaths = new HashSet<AbsolutePath>();
    }

    /// <summary>
    /// Reserve a temp file at the given file name under the system temp directory.
    /// Only paths created through this method are readable or deletable via absolute-path APIs on this instance.
    /// </summary>
    public AbsolutePath CreateTempFile(string fileName)
    {
        _CheckTempFileName(fileName);
        var tempPath = new AbsolutePath(Path.Combine(_TempRoot.FullPath, fileName));
        _RegisterOwnedTempPath(tempPath);
        return tempPath;
    }

    /// <summary>Delete an owned temp file if it exists and remove it from this instance's registry.</summary>
    public void DeleteOwnedTempFile(AbsolutePath path)
    {
        if (path == null)
        {
            throw new ArgumentNullException(nameof(path));
        }

        _EnsureOwnedTempPath(path);
        if (_FileExistsAbsolute(path))
        {
            _DeleteFileAbsolute(path);
        }

        _OwnedTempPaths.Remove(path);
    }

    public async Task WriteAllTextAsync(
        RelativePath relativePath,
        string content,
        CancellationToken cancellationToken)
    {
        await _WriteAllTextAsyncAbsolute(_ResolveAllowedAbsolutePath(relativePath), content, cancellationToken)
            .ConfigureAwait(false);
    }

    public void WriteAllLines(RelativePath relativePath, IReadOnlyList<string> lines)
    {
        if (lines == null)
        {
            throw new ArgumentNullException(nameof(lines));
        }

        _WriteAllLinesAbsolute(_ResolveAllowedAbsolutePath(relativePath), lines);
    }

    #region Private Methods

    private AbsolutePath _ResolveAllowedAbsolutePath(RelativePath relativePath)
    {
        if (relativePath == null)
        {
            throw new ArgumentNullException(nameof(relativePath));
        }

        return _EnsureAccessAllowed(relativePath.ToAbsolute());
    }

    protected override AbsolutePath _EnsureAccessAllowed(AbsolutePath fullPath)
    {
        if (fullPath == null)
        {
            throw new ArgumentNullException(nameof(fullPath));
        }

        if (fullPath.IsUnder(Root) || _IsOwnedTempPath(fullPath))
        {
            return fullPath;
        }

        throw new InvalidOperationException(
            "File access denied: path must resolve under the project root or an owned temp file created by this ProjectFileSystem.");
    }

    private void _RegisterOwnedTempPath(AbsolutePath path)
    {
        _OwnedTempPaths.Add(path);
    }

    private bool _IsOwnedTempPath(AbsolutePath fullPath)
    {
        return _OwnedTempPaths.Contains(fullPath);
    }

    private void _EnsureOwnedTempPath(AbsolutePath path)
    {
        if (!_IsOwnedTempPath(path))
        {
            throw new InvalidOperationException(
                "Temp file access denied: path was not created by CreateTempFile on this ProjectFileSystem.");
        }
    }

    private static void _CheckTempFileName(string fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName))
        {
            throw new ArgumentException("fileName must not be empty.", nameof(fileName));
        }

        if (!string.Equals(Path.GetFileName(fileName), fileName, StringComparison.Ordinal))
        {
            throw new ArgumentException("fileName must not contain directory separators.", nameof(fileName));
        }

        if (fileName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            throw new ArgumentException("fileName contains invalid characters.", nameof(fileName));
        }
    }

    private static void _WriteAllLinesAbsolute(AbsolutePath fullPath, IReadOnlyList<string> lines)
    {
        File.WriteAllLines(fullPath.FullPath, lines);
    }

    private static Task _WriteAllTextAsyncAbsolute(
        AbsolutePath fullPath,
        string content,
        CancellationToken cancellationToken)
    {
        return File.WriteAllTextAsync(fullPath.FullPath, content, cancellationToken);
    }

    private static void _DeleteFileAbsolute(AbsolutePath fullPath)
    {
        File.Delete(fullPath.FullPath);
    }

    #endregion Private Methods
}
