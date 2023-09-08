
from argparse import ArgumentParser, Namespace
from edk2toolext.environment.reporttypes.base_report import Report
from edk2toollib.database import Edk2DB
from edk2toolext.environment.reporttypes import templates
import io
try:
    from jinja2 import Environment, FileSystemLoader
    import plotly.graph_objects as go
except ImportError as e:
    print(e)
    print("WARNING: This report requires pip modules not installed with edk2-pytool-extensions:")
    print("  Run the following command: `pip install jinja2 plotly`")
    exit(-1)


QUERY = """
WITH variable AS (
    SELECT
        ? AS env -- VARIABLE: Change this to the environment parse you care about
)
SELECT
    package.repository AS "Repository",
    inf.package AS "Package",
    inf_list.path AS "INF Path",
    junction.key2 AS "Source Path",
    source.total_lines AS "Code Line Count",
    CASE
        WHEN inf.library_class IS NULL THEN TRUE
        ELSE FALSE
    END AS "Component"
FROM
    (
        SELECT
            DISTINCT instanced_inf.path
        FROM
            variable,
            instanced_fv
            JOIN junction ON instanced_fv.id = junction.key1
            AND junction.table1 = 'instanced_fv'
            AND junction.table2 = 'inf'
            JOIN instanced_inf ON instanced_inf.component = junction.key2
        WHERE
            instanced_fv.env = variable.env
    ) inf_list,
    variable
    JOIN junction ON junction.key1 = inf_list.path
    AND junction.table2 = 'source'
    AND junction.env = variable.env
    LEFT JOIN source ON source.path = junction.key2
    LEFT JOIN inf ON inf.path = inf_list.path
    LEFT JOIN package ON inf.package = package.name
ORDER BY
    package.repository,
    package.name,
    inf_list.path
"""

class UsageReport(Report):
    """A report that generates a INF usage report for a specific build."""
    def report_info(self):
        """Returns the report standard information.

        Returns:
            (str, str): A tuple of (name, description)
        """
        return ("usage", "Generates a report of INF usage for a specific build.")

    def add_cli_options(self, parserobj: ArgumentParser):
        """Configure command line arguments for this report."""
        parserobj.add_argument("-e", "-env", dest="env_id", action="store", help = "The environment id to generate the report for. Defaults to the latest environment.")
        parserobj.add_argument("-o", "-output", dest="output", action="store", help = "The output file to write the report to. Defaults to 'usage_report.html'.", default=None)

    def run_report(self, db: Edk2DB, args: Namespace):
        """Generate the Usage report."""
        env_id = args.env_id or db.connection.execute("SELECT id FROM environment ORDER BY date DESC LIMIT 1;").fetchone()[0]

        # Vars for html template
        env = Environment(loader=FileSystemLoader(templates.__path__))
        template = env.get_template("usage_report_template.html")

        # This is the data that gets passed to the html template
        data = {}

        data["version"] = db.connection.execute("SELECT version FROM environment WHERE id = ?;", (env_id,)).fetchone()[0]
        data["env"] = self._get_env_vars(db.connection, env_id)

        # Split up the data from the database
        lib_infs = {}
        comp_infs = {}
        inf_list = set()
        for repo, package, inf, _src, _lc, is_component in db.connection.execute(QUERY, (env_id,)).fetchall():
            inf_list.add((repo, package, inf))
            if is_component:
                d = comp_infs
            else:
                d = lib_infs
            if repo not in d:
                d[repo] = [inf]
            else:
                d[repo].append(inf)

        # Add the inf_list to the data
        data["inf_list"] = inf_list

        # Build the reports
        reports = [
            ("lib_pie_chart", lib_infs, "Library Usage Per Repository"),
            ("comp_pie_chart", comp_infs, "Component Usage Per Repository")
        ]
        for key, value, title in reports:
            # Build the figure
            labels = [key for key in value.keys()]
            values = [len(set(value)) for value in value.values()]
            fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole = .3, title=title, titleposition="top center")])

            # Write the html
            html = io.StringIO()
            fig.write_html(html, full_html=False, include_plotlyjs=False)
            html.seek(0)

            # Add the html to the data dictionary
            data[key] = html.read()

        # Open the template and write the html with the data
        html_output = template.render(**data)
        path_out = args.output or data["env"].get("PLATFORM_NAME", None) or "usage_report.html"
        if not path_out.endswith(".html"):
            path_out += ".html"
        with open(path_out, 'w') as f:
            f.write(html_output)

    def _get_env_vars(self, connection, env_id):
        env_vars = {}
        results = connection.execute("SELECT key, value FROM environment_values WHERE id = ?;", (env_id,)).fetchall()
        for key, value in results:
            env_vars[key] = value
        return env_vars
