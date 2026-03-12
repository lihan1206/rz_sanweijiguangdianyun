import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

interface Props {
  points: number[][];
}

export function PointCloudViewer({ points }: Props): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = 420;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#f6fbff');

    const camera = new THREE.PerspectiveCamera(65, width / height, 0.1, 1000);
    camera.position.set(20, 20, 20);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    containerRef.current.innerHTML = '';
    containerRef.current.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const grid = new THREE.GridHelper(30, 20, '#8aa6bf', '#d6e4f0');
    scene.add(grid);

    const axesHelper = new THREE.AxesHelper(12);
    scene.add(axesHelper);

    if (points.length > 0) {
      const positions = new Float32Array(points.length * 3);
      points.forEach((point, index) => {
        positions[index * 3] = point[0];
        positions[index * 3 + 1] = point[1];
        positions[index * 3 + 2] = point[2];
      });

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

      const material = new THREE.PointsMaterial({
        color: '#1677ff',
        size: 0.12,
        sizeAttenuation: true
      });

      const cloud = new THREE.Points(geometry, material);
      scene.add(cloud);
    }

    const light = new THREE.DirectionalLight(0xffffff, 1);
    light.position.set(15, 20, 10);
    scene.add(light);

    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);

    let animationId = 0;
    const animate = (): void => {
      animationId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const onResize = (): void => {
      if (!containerRef.current) return;
      const newWidth = containerRef.current.clientWidth;
      camera.aspect = newWidth / height;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, height);
    };

    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', onResize);
      controls.dispose();
      renderer.dispose();
    };
  }, [points]);

  return <div ref={containerRef} style={{ width: '100%', borderRadius: 12, overflow: 'hidden' }} />;
}
