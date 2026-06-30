using System.Text.RegularExpressions;
using Xunit;

namespace ProofAgent.Tests;

public class IOIsolationPolicyTests
{
    [Fact]
    public void MainProject_DoesNotCallFileOrDirectoryStaticsOutsideProjectFileSystem()
    {
        var repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
        var violations = new List<string>();
        var filePattern = new Regex(
            @"\bFile\.(Exists|Read|Write|Delete|Create|Open|Append|Copy|Move|Get|Set)",
            RegexOptions.CultureInvariant);
        var directoryPattern = new Regex(
            @"\bDirectory\.(Create|Exists|Delete|Get|Move|Enumerate)",
            RegexOptions.CultureInvariant);

        foreach (var csPath in _EnumerateMainProjectCsFiles(repoRoot))
        {
            var fileName = Path.GetFileName(csPath);
            if (string.Equals(fileName, "ProjectFileSystem.cs", StringComparison.Ordinal) ||
                string.Equals(fileName, "ReadOnlyFileSystem.cs", StringComparison.Ordinal) ||
                string.Equals(fileName, "Program.cs", StringComparison.Ordinal))
            {
                continue;
            }

            var lines = File.ReadAllLines(csPath);
            var relativePath = Path.GetRelativePath(repoRoot, csPath);
            for (var i = 0; i < lines.Length; i++)
            {
                var line = lines[i];
                if (filePattern.IsMatch(line) || directoryPattern.IsMatch(line))
                {
                    violations.Add($"{relativePath}:{i + 1}: {line.Trim()}");
                }
            }
        }

        Assert.True(
            violations.Count == 0,
            "Direct System.IO.File/Directory usage outside ReadOnlyFileSystem, ProjectFileSystem, or Program:\n" +
            string.Join(Environment.NewLine, violations));
    }

    private static IEnumerable<string> _EnumerateMainProjectCsFiles(string repoRoot)
    {
        var excludeDirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "ProofAgent.Tests",
            "bin",
            "obj",
            ".git",
        };

        foreach (var path in Directory.EnumerateFiles(repoRoot, "*.cs", SearchOption.AllDirectories))
        {
            var parts = path.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (parts.Any(excludeDirs.Contains))
            {
                continue;
            }

            yield return path;
        }
    }
}
