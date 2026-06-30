using System.Text.Json;
using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class ProjectFileToolsTests
{
    private static int _DefaultErrorSourceLinesBefore =>
        ReflectionTestAccess.GetStaticFieldNonPublic<int>(typeof(CoqMultiErrorChecker), "_DefaultErrorSourceLinesBefore")!;

    private static int _DefaultErrorSourceLinesAfter =>
        ReflectionTestAccess.GetStaticFieldNonPublic<int>(typeof(CoqMultiErrorChecker), "_DefaultErrorSourceLinesAfter")!;

    [Fact]
    public async Task SearchCoqFilesRegexTool_FindsMatches_DefaultPathLineListing()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchCoq_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "A", "B"));
        File.WriteAllText(Path.Combine(root, "Top.v"), "needle at top\nbeta\n");
        File.WriteAllLines(
            Path.Combine(root, "A", "B", "Nested.v"),
            new[] { "x", "y", "needle here", "z" });
        File.WriteAllText(Path.Combine(root, "A", "B", "NotV.txt"), "needle");

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            using var args = JsonDocument.Parse("""{"pattern":"needle"}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("A/B/Nested.v:3", result, StringComparison.Ordinal);
            Assert.Contains("Top.v:1", result, StringComparison.Ordinal);
            Assert.DoesNotContain("needle here", result, StringComparison.Ordinal);
            Assert.DoesNotContain('\\', result);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_IsShowContextOne_ReturnsPathAndSnippetPerMatch()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchCoqCtx_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "A", "B"));
        File.WriteAllText(Path.Combine(root, "Top.v"), "needle at top\nbeta\n");
        File.WriteAllLines(
            Path.Combine(root, "A", "B", "Nested.v"),
            new[] { "x", "y", "needle here", "z" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            using var args = JsonDocument.Parse("""{"pattern":"needle","isShowContext":true}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("A/B/Nested.v", result, StringComparison.Ordinal);
            Assert.Contains(Environment.NewLine + "3: needle here", result, StringComparison.Ordinal);
            Assert.Contains("Top.v", result, StringComparison.Ordinal);
            Assert.Contains(Environment.NewLine + "1: needle at top", result, StringComparison.Ordinal);
            Assert.Contains($"{Environment.NewLine}{Environment.NewLine}", result, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_ContextZero_EllipsisAroundSingleLineWindow()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchCtx0_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(
            Path.Combine(root, "M.v"),
            new[] { "a", "b", "needle mid", "c", "d" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 0);
            using var args = JsonDocument.Parse("""{"pattern":"needle","isShowContext":true}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            var expected = string.Join(
                Environment.NewLine,
                new[] { "M.v", "...", "3: needle mid", "..." });
            Assert.Equal(expected, result);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_FirstLineHit_NoLeadingEllipsis()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchFirstHit_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(
            Path.Combine(root, "F.v"),
            new[] { "first needle", "L2", "L3", "L4" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 1);
            using var args = JsonDocument.Parse("""{"pattern":"needle","isShowContext":true}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.StartsWith($"F.v{Environment.NewLine}", result, StringComparison.Ordinal);
            Assert.DoesNotContain($"F.v{Environment.NewLine}...", result, StringComparison.Ordinal);
            Assert.Contains("1: first needle", result, StringComparison.Ordinal);
            Assert.EndsWith("...", result, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_NoMatches_ReturnsNoMatchesFoundMessage()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchEmpty_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, "Only.v"), "no match text");

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            using var args = JsonDocument.Parse("""{"pattern":"zzz"}""");
            Assert.Equal("No matches found.", await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_MaxMatchesTruncation_AppendsPaginationFooter()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchTrunc_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var lines = Enumerable.Range(1, 5).Select(i => $"needle {i}").ToArray();
        File.WriteAllLines(Path.Combine(root, "Many.v"), lines);

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 0);
            using var args = JsonDocument.Parse("""{"pattern":"needle","maxMatches":2}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("Many.v:1", result, StringComparison.Ordinal);
            Assert.Contains("Many.v:2", result, StringComparison.Ordinal);
            Assert.DoesNotContain("Many.v:3", result, StringComparison.Ordinal);
            Assert.Contains("[Showing hits 1-2 of 5;", result, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_Offset_ReturnsSecondPage()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchOffset_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var lines = Enumerable.Range(1, 4).Select(i => $"needle {i}").ToArray();
        File.WriteAllLines(Path.Combine(root, "P.v"), lines);

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 0);
            using var args = JsonDocument.Parse("""{"pattern":"needle","offset":2,"maxMatches":10}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("P.v:3", result, StringComparison.Ordinal);
            Assert.Contains("P.v:4", result, StringComparison.Ordinal);
            Assert.DoesNotContain("P.v:1", result, StringComparison.Ordinal);
            Assert.DoesNotContain("P.v:2", result, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_OffsetPastLastHit_ReturnsNoMatchesOnPageMessage()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchPast_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "Q.v"), new[] { "needle once" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 0);
            using var args = JsonDocument.Parse("""{"pattern":"needle","offset":5}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("No matches on this page.", result, StringComparison.Ordinal);
            Assert.Contains("offset 5 is past the last hit", result, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task SearchCoqFilesRegexTool_IsShowContextOne_ManyHits_TruncatesOutputByCharLimit()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentSearchCharLim_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var lines = Enumerable.Range(1, 800).Select(static i => "needle padding line content").ToArray();
        File.WriteAllLines(Path.Combine(root, "Huge.v"), lines);

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new SearchFilesTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 0);
            using var args = JsonDocument.Parse("""{"pattern":"needle","isShowContext":true,"maxMatches":800}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("[Output truncated at 10000 characters;", result, StringComparison.Ordinal);
            Assert.True(result.Length > 10000);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ProjectFileSystem_SearchCoqFilesForRegex_OffsetAndTotalHitCount()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentFsSearch_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "T.v"), new[] { "a", "hit", "hit", "b" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var regex = new System.Text.RegularExpressions.Regex("hit");
            var page = fs.SearchByRegex(regex, offset: 1, maxMatches: 10);
            Assert.Equal(2, page.TotalHitCount);
            Assert.Single(page.Hits);
            Assert.Equal(3, page.Hits[0].LineNumberOneBased);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReadFileTool_Range_ReturnsExactLines()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentReadFile_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var path = Path.Combine(root, "X.v");
        File.WriteAllLines(path, new[] { "l1", "l2", "l3", "l4" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new ReadFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            using var args = JsonDocument.Parse("""{"path":"X.v","startLine":2,"endLine":3}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Equal(
                string.Join(Environment.NewLine, new[] { "...", "2: l2", "3: l3", "..." }),
                result);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReadFileTool_EndLineOutOfRange_ClampsToEof()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentReadFileClamp_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var path = Path.Combine(root, "X.v");
        File.WriteAllLines(path, new[] { "l1", "l2", "l3", "l4" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new ReadFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            using var args = JsonDocument.Parse("""{"path":"X.v","startLine":3,"endLine":100}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Equal(
                string.Join(Environment.NewLine, new[] { "...", "3: l3", "4: l4" }),
                result);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReadFileTool_PathEscapesRootAndTemp_IsRejected()
    {
        // Root deliberately outside the system temp directory so that escaping it also escapes temp.
        var root = Path.Combine(AppContext.BaseDirectory, "ProofAgentEscape_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        File.WriteAllLines(Path.Combine(root, "Ok.v"), new[] { "x" });

        try
        {
            var fs = new ProjectFileSystem(root);
            var tool = new ReadFileTool(PromptTestFixtures.CreateToolDeclarationLoader(TestInjectedLogger.CreateFatalOnly()));
            var ctx = ToolExecutionContextTestFixtures.CreateFileOnly(fs, searchHitContextLines: 2);
            using var args = JsonDocument.Parse("""{"path":"../Outside.v","startLine":1,"endLine":1}""");
            var result = await tool.RunAsync(ctx, args.RootElement.Clone(), CancellationToken.None);
            Assert.Contains("project root", result, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task LinesAround_IncludesContextAndCaret()
    {
        var lines = new[] { "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9", "l10" };
        var text = _RenderSnippet(
            lines,
            10,
            _DefaultErrorSourceLinesBefore,
            _DefaultErrorSourceLinesAfter,
            0);
        Assert.Equal(
            string.Join(
                Environment.NewLine,
                new[]
                {
                    "...",
                    "4: l4",
                    "5: l5",
                    "6: l6",
                    "7: l7",
                    "8: l8",
                    "9: l9",
                    "10: l10",
                    "    ^",
                }),
            text);
    }

    [Fact]
    public async Task LinesAround_CaretAlignsToZeroBasedColumn()
    {
        var lines = new[] { "  alpha beta" };
        var text = _RenderSnippet(lines, 1, 0, _DefaultErrorSourceLinesAfter, 3);
        Assert.Equal(
            string.Join(Environment.NewLine, new[] { "1:   alpha beta", "      ^" }),
            text);
    }

    [Fact]
    public async Task LinesAround_IncludesLinesAfterError_NotCountingCaret()
    {
        var lines = Enumerable.Range(1, 15).Select(i => $"l{i}").ToArray();
        var text = _RenderSnippet(
            lines,
            10,
            _DefaultErrorSourceLinesBefore,
            _DefaultErrorSourceLinesAfter,
            0);
        Assert.Contains("10: l10", text, StringComparison.Ordinal);
        Assert.Contains("    ^", text, StringComparison.Ordinal);
        Assert.Contains("11: l11", text, StringComparison.Ordinal);
        Assert.Contains("12: l12", text, StringComparison.Ordinal);
        Assert.Contains("13: l13", text, StringComparison.Ordinal);
        Assert.DoesNotContain("14: l14", text, StringComparison.Ordinal);
        Assert.Contains("...", text, StringComparison.Ordinal);
    }

    [Fact]
    public async Task LinesAround_AtFileEnd_NoTrailingEllipsisWhenAfterExhausted()
    {
        var lines = new[] { "a", "b", "c" };
        var text = _RenderSnippet(
            lines,
            3,
            _DefaultErrorSourceLinesBefore,
            _DefaultErrorSourceLinesAfter,
            0);
        var lineList = text.Split(Environment.NewLine);
        Assert.Equal("3: c", lineList[^2]);
        Assert.Equal("   ^", lineList[^1]);
    }

    [Fact]
    public async Task LinesAround_WindowFlagsAndRangeClampToFile()
    {
        var fileSystem = new ProjectFileSystem(Path.GetTempPath());
        var lines = new[] { "a", "b", "c", "d", "e" };

        var window = fileSystem.LinesAround(lines, 3, 1, 1);
        Assert.Equal(2, window.StartLine);
        Assert.Equal(4, window.EndLine);
        Assert.True(window.HasLeadingEllipsis);
        Assert.True(window.HasTrailingEllipsis);
        Assert.Equal(new[] { "b", "c", "d" }, window.Lines);

        var startWindow = fileSystem.LinesAround(lines, 1, 6, 2);
        Assert.Equal(1, startWindow.StartLine);
        Assert.Equal(3, startWindow.EndLine);
        Assert.False(startWindow.HasLeadingEllipsis);
        Assert.True(startWindow.HasTrailingEllipsis);
    }

    [Fact]
    public async Task RelativePath_AbsoluteOrDotSlash_NormalizeToPosixRelative()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentResolvePath_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "sub"));
        var absolute = Path.Combine(root, "sub", "File.v");
        try
        {
            var fileSystem = new ProjectFileSystem(root);
            Assert.Equal("sub/File.v", fileSystem.Rel(absolute).PosixPath);
            Assert.Equal("sub/File.v", fileSystem.Rel("./sub/File.v").PosixPath);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ProjectFileSystem_ReadOutsideRootAndTemp_Throws()
    {
        // Root outside system temp so an outside-and-not-temp absolute path can be expressed.
        var root = Path.Combine(AppContext.BaseDirectory, "ProofAgentResolveOutside_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var fileSystem = new ProjectFileSystem(root);
            var outside = new AbsolutePath(Path.Combine(AppContext.BaseDirectory, "ProofAgentOutside_" + Guid.NewGuid().ToString("N") + ".v"));
            Assert.Throws<InvalidOperationException>(() => fileSystem.ReadAllText(outside));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ProjectFileSystem_OwnedTempFileOutsideRoot_IsReadableAfterCreateTempFile()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "ProofAgentTempAllowed_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var unownedTempFile = new AbsolutePath(Path.Combine(Path.GetTempPath(), "ProofAgentTempUnowned_" + Guid.NewGuid().ToString("N") + ".out"));
        try
        {
            File.WriteAllText(unownedTempFile.FullPath, "other-process");
            var fileSystem = new ProjectFileSystem(root);
            var ownedOutput = fileSystem.CreateTempFile("ProofAgentTempOwned_" + Guid.NewGuid().ToString("N") + ".out");
            File.WriteAllText(ownedOutput.FullPath, "env-capture");
            Assert.True(fileSystem.Exists(ownedOutput));
            Assert.Equal("env-capture", fileSystem.ReadAllText(ownedOutput));
            Assert.Throws<InvalidOperationException>(() => fileSystem.ReadAllText(unownedTempFile));
            Assert.Throws<InvalidOperationException>(() => fileSystem.Exists(unownedTempFile));
        }
        finally
        {
            if (File.Exists(unownedTempFile.FullPath))
            {
                File.Delete(unownedTempFile.FullPath);
            }

            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ProjectFileSystem_DeleteOwnedTempFileIfExists_UnregisteredPath_Throws()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "ProofAgentTempDelete_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var foreignTemp = new AbsolutePath(Path.Combine(Path.GetTempPath(), "ProofAgentTempForeign_" + Guid.NewGuid().ToString("N")));
        try
        {
            var fileSystem = new ProjectFileSystem(root);
            Assert.Throws<InvalidOperationException>(() => fileSystem.DeleteOwnedTempFile(foreignTemp));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    private static string _RenderSnippet(
        string[] lines,
        int errorLine,
        int linesBefore,
        int linesAfter,
        int errorColumnZeroBased)
    {
        var fileSystem = new ProjectFileSystem(Path.GetTempPath());
        var window = fileSystem.LinesAround(lines, errorLine, linesBefore, linesAfter);
        var error = PathTests.Error("X.v", errorLine, errorColumnZeroBased, "message");
        return ReflectionTestAccess.InvokeStaticNonPublic<string>(
            typeof(CoqMultiErrorChecker),
            "_RenderSnippet",
            new object?[] { window, error })!;
    }
}
