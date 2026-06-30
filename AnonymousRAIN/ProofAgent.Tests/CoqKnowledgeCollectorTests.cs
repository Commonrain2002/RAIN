using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class CoqKnowledgeCollectorTests
{
    [Fact]
    public async Task GetDefinitions_SplitsWhitespaceAndTrimsBoundaryPunctuation()
    {
        var tempDir = _CreateTempProjectDirectory();
        try
        {
            var collector = _CreateCollector(
                tempDir,
                new Dictionary<string, IReadOnlyList<CoqSentence>>
                {
                    ["Defs.v"] = new[]
                    {
                        _Sentence(CoqSentenceVernacType.Definition, "foo", 1, 1, "Definition foo := 0."),
                        _Sentence(CoqSentenceVernacType.Definition, "bar", 3, 3, "Definition bar := 1."),
                    },
                });

            var failures = new[]
            {
                _Failure(" (foo),   [bar]. "),
            };

            var definitions = collector.GetDefinitions(failures);

            Assert.Equal(2, definitions.Count);
            Assert.Contains(definitions, definition => definition.Text == "Definition foo := 0.");
            Assert.Contains(definitions, definition => definition.Text == "Definition bar := 1.");
        }
        finally
        {
            _DeleteTempDirectoryBestEffort(tempDir);
        }
    }

    [Fact]
    public async Task GetDefinitions_WhenBelowThreshold_ExpandsFromDefinitionText()
    {
        var tempDir = _CreateTempProjectDirectory();
        try
        {
            var collector = _CreateCollector(
                tempDir,
                new Dictionary<string, IReadOnlyList<CoqSentence>>
                {
                    ["Defs.v"] = new[]
                    {
                        _Sentence(CoqSentenceVernacType.Definition, "alpha", 1, 1, "Definition alpha := beta."),
                        _Sentence(CoqSentenceVernacType.Definition, "beta", 2, 2, "Definition beta := 42."),
                    },
                });

            var failures = new[]
            {
                _Failure("alpha"),
            };

            var definitions = collector.GetDefinitions(failures);

            Assert.Equal(2, definitions.Count);
            Assert.Contains(definitions, definition => definition.Text == "Definition alpha := beta.");
            Assert.Contains(definitions, definition => definition.Text == "Definition beta := 42.");
        }
        finally
        {
            _DeleteTempDirectoryBestEffort(tempDir);
        }
    }

    [Fact]
    public async Task GetDefinitions_ReturnsAtMostTenDefinitionsAndDeduplicates()
    {
        var tempDir = _CreateTempProjectDirectory();
        try
        {
            var sentences = new List<CoqSentence>();
            var envTokens = new List<string>();
            for (var i = 1; i <= 12; i++)
            {
                var name = "d" + i;
                envTokens.Add(name);
                sentences.Add(_Sentence(CoqSentenceVernacType.Definition, name, i, i, $"Definition {name} := {i}."));
            }

            var collector = _CreateCollector(
                tempDir,
                new Dictionary<string, IReadOnlyList<CoqSentence>>
                {
                    ["Defs.v"] = sentences,
                });

            var failures = new[]
            {
                _Failure(string.Join(" ", envTokens) + " d1 d2"),
            };

            var definitions = collector.GetDefinitions(failures);

            Assert.Equal(10, definitions.Count);
            var definitionKeys = definitions
                .Select(definition => $"{definition.RelativeCoqFilePath}:{definition.StartLineOneBased}:{definition.EndLineOneBased}")
                .Distinct(StringComparer.Ordinal)
                .ToArray();
            Assert.Equal(10, definitionKeys.Length);
        }
        finally
        {
            _DeleteTempDirectoryBestEffort(tempDir);
        }
    }

    private static CoqRunCheckFailure _Failure(string environmentText)
    {
        return new CoqRunCheckFailure
        {
            Check = new CoqCheck(CoqCheckType.Failed, PathTests.Error("Target.v", 1, 0, "error"), "raw", 30),
            EnvironmentText = environmentText,
            SourceSnippet = "",
        };
    }

    private static CoqSentence _Sentence(
        CoqSentenceVernacType vernacType,
        string name,
        int startLineOneBased,
        int endLineOneBased,
        string text)
    {
        return new CoqSentence
        {
            VernacType = vernacType,
            Name = name,
            StartLineOneBased = startLineOneBased,
            EndLineOneBased = endLineOneBased,
            Text = text,
        };
    }

    private static CoqKnowledgeCollector _CreateCollector(
        string tempDir,
        Dictionary<string, IReadOnlyList<CoqSentence>> sentencesByPath)
    {
        foreach (var relativePath in sentencesByPath.Keys)
        {
            File.WriteAllText(Path.Combine(tempDir, relativePath), "");
        }

        var fileSystem = new ProjectFileSystem(tempDir);
        var definitionDatabase = new DefinitionDatabase(TestInjectedLogger.CreateFatalOnly());
        _PopulateDefinitionDatabase(definitionDatabase, fileSystem, sentencesByPath);
        return new CoqKnowledgeCollector(definitionDatabase, TestInjectedLogger.CreateFatalOnly());
    }

    private static void _PopulateDefinitionDatabase(
        DefinitionDatabase definitionDatabase,
        ProjectFileSystem fileSystem,
        Dictionary<string, IReadOnlyList<CoqSentence>> sentencesByPath)
    {
        foreach (var entry in sentencesByPath)
        {
            var relativePath = new RelativePath(entry.Key, fileSystem.Root);
            foreach (var sentence in entry.Value)
            {
                definitionDatabase.TryAddDefinition(relativePath, sentence);
            }
        }
    }

    private static string _CreateTempProjectDirectory()
    {
        var tempDir = Path.Combine(
            Path.GetTempPath(),
            "ProofAgentCoqKnowledgeCollector_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        return tempDir;
    }

    private static void _DeleteTempDirectoryBestEffort(string tempDir)
    {
        try
        {
            Directory.Delete(tempDir, true);
        }
        catch
        {
            // best-effort
        }
    }
}
