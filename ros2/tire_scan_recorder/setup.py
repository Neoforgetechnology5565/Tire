from setuptools import setup

package_name = "tire_scan_recorder"
setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/record_l2.launch.py", "launch/analyze_bag.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={"console_scripts": ["scan_recorder = tire_scan_recorder.recorder:main"]},
)
